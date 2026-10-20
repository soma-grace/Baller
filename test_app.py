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
            "budget_type": "overall",
            "category": "",
            "amount": Decimal("50000"),
            "month": "2026-10",
        }

        response = main.budget_submit(self.request, **data, db=self.db)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/budgets?month=2026-10")

        data["amount"] = Decimal("60000")
        response = main.budget_submit(self.request, **data, db=self.db)
        self.assertEqual(response.status_code, 303)

        budgets = self.db.query(Budget).all()
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0].amount, Decimal("60000.00"))

        page = main.budgets_page(self.request, month="2026-10", db=self.db)
        self.assertEqual(page.status_code, 200)
        self.assertIn("₦60000.00", page.body.decode())

    def test_category_budget_and_expense_form_are_saved_and_filterable(self):
        budget_response = main.budget_submit(
            self.request,
            budget_type="category",
            category="food",
            amount=Decimal("12000"),
            month="2026-10",
            db=self.db,
        )
        self.assertEqual(budget_response.status_code, 303)

        expense_response = main.add_expense_submit(
            self.request,
            amount=Decimal("1250.50"),
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
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 31),
            db=self.db,
        )
        self.assertEqual(page.status_code, 200)
        self.assertIn("Lunch at work", page.body.decode())
        self.assertIn("₦1250.50", page.body.decode())

        budget_page = main.budgets_page(
            self.request, month="2026-10", db=self.db
        )
        self.assertIn("Food", budget_page.body.decode())
        self.assertIn("₦1250.50 spent", budget_page.body.decode())

    def test_budget_submission_requires_a_signed_in_user(self):
        self.request.scope["session"] = {}
        response = main.budget_submit(
            self.request,
            budget_type="overall",
            category="",
            amount=Decimal("1000"),
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
