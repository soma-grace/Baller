import os
import unittest
from datetime import date
from decimal import Decimal

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from database import Base
import main
from main import app
from models import Budget, User

main.engine.dispose()


class AppInteractionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        testing_session = sessionmaker(bind=self.engine, autoflush=False)
        self.db = testing_session()
        user = User(
            full_name="Test User",
            email="test@example.com",
            password_hash="not-used",
        )
        self.db.add(user)
        self.db.commit()
        self.request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/",
                "headers": [],
                "query_string": b"",
            }
        )
        self.request.scope["session"] = {"user_id": user.id}

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_budget_form_persists_and_updates_monthly_budget(self):
        data = {
            "category": "",
            "amount": "50,000",
            "month": "2026-10",
        }

        response = main.budget_submit(self.request, **data, db=self.db)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/budgets?month=2026-10")

        data["amount"] = "60,000"
        response = main.budget_submit(self.request, **data, db=self.db)
        self.assertEqual(response.status_code, 303)

        budgets = self.db.query(Budget).all()
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0].amount, Decimal("60000.00"))

        page = main.budgets_page(self.request, month="2026-10", db=self.db)
        self.assertEqual(page.status_code, 200)
        self.assertIn("₦60,000.00", page.body.decode())

    def test_budget_category_and_expense_form_are_saved_and_filterable(self):
        budget_response = main.budget_submit(
            self.request,
            category="food",
            amount="12,000",
            month="2026-10",
            db=self.db,
        )
        self.assertEqual(budget_response.status_code, 303)

        expense_response = main.add_expense_submit(
            self.request,
            amount="1,250.50",
            category="food",
            expense_type="need",
            spent_at=date(2026, 10, 12),
            note="Lunch at work",
            db=self.db,
        )
        self.assertEqual(expense_response.status_code, 303)
        self.assertEqual(expense_response.headers["location"], "/transactions")

        page = main.transactions_page(
            self.request,
            search="Lunch",
            category="food",
            expense_type="need",
            start_date="2026-10-01",
            end_date="2026-10-31",
            db=self.db,
        )
        self.assertEqual(page.status_code, 200)
        self.assertIn("Lunch at work", page.body.decode())
        self.assertIn("₦1,250.50", page.body.decode())

        budget_page = main.budgets_page(
            self.request, month="2026-10", db=self.db
        )
        self.assertIn("₦1,250.50", budget_page.body.decode())
        self.assertNotIn("Category budgets", budget_page.body.decode())
        self.assertNotIn("budget_type", budget_page.body.decode())
        self.assertEqual(self.db.query(Budget).one().budget_type, "overall")

    def test_future_expenses_are_rejected(self):
        with self.assertRaises(main.HTTPException) as error:
            main.add_expense_submit(
                self.request,
                amount="100",
                category="food",
                expense_type="need",
                spent_at=date.today() + main.timedelta(days=1),
                note="Tomorrow lunch",
                db=self.db,
            )
        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("future", error.exception.detail)

        page = main.add_expense_page(self.request)
        self.assertIn(
            f'max="{date.today().isoformat()}"',
            page.body.decode(),
        )

    def test_transaction_filters_apply_together_and_reject_invalid_ranges(self):
        user_id = self.request.scope["session"]["user_id"]
        matches = main.Expense(
            user_id=user_id,
            amount=Decimal("1250"),
            category="food",
            expense_type="need",
            note="Work lunch",
            expense_date=date(2026, 10, 12),
        )
        non_match = main.Expense(
            user_id=user_id,
            amount=Decimal("2000"),
            category="shopping",
            expense_type="want",
            note="Shoes",
            expense_date=date(2026, 10, 13),
        )
        self.db.add_all([matches, non_match])
        self.db.commit()

        page = main.transactions_page(
            self.request,
            search="lunch",
            category="food",
            expense_type="need",
            start_date="2026-10-01",
            end_date="2026-10-31",
            db=self.db,
        )
        html = page.body.decode()
        self.assertIn("Work lunch", html)
        self.assertNotIn("Shoes", html)
        self.assertIn('value="lunch"', html)
        self.assertIn('value="food" selected', html)

        with self.assertRaises(main.HTTPException) as error:
            main.transactions_page(
                self.request,
                start_date="2026-10-31",
                end_date="2026-10-01",
                db=self.db,
            )
        self.assertEqual(error.exception.status_code, 400)

    def test_transaction_filters_accept_empty_date_fields(self):
        user_id = self.request.scope["session"]["user_id"]
        self.db.add(
            main.Expense(
                user_id=user_id,
                amount=Decimal("1250"),
                category="food",
                expense_type="need",
                note="Lunch",
                expense_date=date.today(),
            )
        )
        self.db.commit()

        page = main.transactions_page(
            self.request,
            search="Lunch",
            category="",
            expense_type="",
            start_date="",
            end_date="",
            db=self.db,
        )
        self.assertEqual(page.status_code, 200)
        self.assertIn("Lunch", page.body.decode())
        self.assertIn('name="start_date"', page.body.decode())
        self.assertIn('name="end_date"', page.body.decode())

    def test_amount_parser_accepts_valid_thousands_separators(self):
        self.assertEqual(main.parse_money_amount("20,000"), Decimal("20000"))
        self.assertEqual(main.parse_money_amount("20,000.50"), Decimal("20000.50"))
        with self.assertRaises(main.HTTPException):
            main.parse_money_amount("20,00")

    def test_budget_submission_requires_a_signed_in_user(self):
        self.request.scope["session"] = {}
        response = main.budget_submit(
            self.request,
            category="",
            amount="1,000",
            month=date.today().strftime("%Y-%m"),
            db=self.db,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login")

    def test_expected_form_routes_are_registered(self):
        routes = {
            (route.path, method)
            for route in app.routes
            for method in (getattr(route, "methods", None) or [])
        }
        self.assertIn(("/budgets", "POST"), routes)
        self.assertIn(("/add-expense", "POST"), routes)
        self.assertIn(("/budgets/{budget_id}/edit", "POST"), routes)

    def test_overall_budget_can_be_edited(self):
        budget = Budget(
            user_id=self.request.scope["session"]["user_id"],
            budget_type="overall",
            category="shopping",
            amount=Decimal("50000"),
            month=date(2026, 10, 1),
        )
        self.db.add(budget)
        self.db.commit()

        response = main.budget_edit(
            budget.id,
            self.request,
            category="shopping",
            amount="60,000",
            month="2026-10",
            db=self.db,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/budgets?month=2026-10")
        self.db.refresh(budget)
        self.assertEqual(budget.amount, Decimal("60000.00"))

        page = main.budgets_page(self.request, month="2026-10", db=self.db)
        self.assertIn(f'data-budget-id="{budget.id}"', page.body.decode())
        self.assertIn('data-amount="60000.00"', page.body.decode())

    def test_budget_edit_cannot_change_another_users_budget(self):
        other_user = User(
            full_name="Other User",
            email="other@example.com",
            password_hash="not-used",
        )
        self.db.add(other_user)
        self.db.commit()
        budget = Budget(
            user_id=other_user.id,
            budget_type="overall",
            category=None,
            amount=Decimal("50000"),
            month=date(2026, 10, 1),
        )
        self.db.add(budget)
        self.db.commit()

        with self.assertRaises(main.HTTPException) as error:
            main.budget_edit(
                budget.id,
                self.request,
                category="",
                amount="60,000",
                month="2026-10",
                db=self.db,
            )
        self.assertEqual(error.exception.status_code, 404)

    def test_dashboard_renders_live_donut_and_budget_progress(self):
        today = date.today()
        month = today.replace(day=1)
        self.db.add(
            Budget(
                user_id=self.request.scope["session"]["user_id"],
                budget_type="overall",
                category="shopping",
                amount=Decimal("50000"),
                month=month,
            )
        )
        self.db.add_all(
            [
                main.Expense(
                    user_id=self.request.scope["session"]["user_id"],
                    amount=Decimal("20000"),
                    category="shopping",
                    expense_type="want",
                    expense_date=today,
                ),
            ]
        )
        self.db.commit()

        page = main.dashboard_page(self.request, db=self.db)
        html = page.body.decode()
        self.assertIn('"color": "#a9b99e"', html)
        self.assertIn("Shopping", html)
        self.assertIn("₦20,000.00 / ₦50,000.00", html)

    def test_dashboard_overall_budget_compares_all_spending(self):
        today = date.today()
        user_id = self.request.scope["session"]["user_id"]
        self.db.add(
            Budget(
                user_id=user_id,
                budget_type="overall",
                category=None,
                amount=Decimal("50000"),
                month=today.replace(day=1),
            )
        )
        self.db.add(
            main.Expense(
                user_id=user_id,
                amount=Decimal("53500"),
                category="food",
                expense_type="need",
                expense_date=today,
            )
        )
        self.db.commit()

        page = main.dashboard_page(self.request, db=self.db)
        html = page.body.decode()
        self.assertIn("₦53,500.00 / ₦50,000.00", html)
        self.assertIn('data-progress="100.0"', html)
        self.assertIn("107.0% of your overall monthly budget used.", html)
