import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import date, datetime, timedelta
from decimal import Decimal
import re
import bcrypt
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from database import Base, engine, get_db
from models import Budget, Expense, User

Base.metadata.create_all(bind=engine)


app = FastAPI(title="Baller")
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}")
EXPENSE_CATEGORIES = (
    "food",
    "shopping",
    "transport",
    "entertainment",
    "bills",
    "subscriptions",
    "health",
    "other",
)
CATEGORY_COLORS = {
    "food": "#354a30",
    "shopping": "#a9b99e",
    "transport": "#d6dfcf",
    "entertainment": "#c18a43",
    "bills": "#6f8497",
    "subscriptions": "#a783a7",
    "health": "#cc7f72",
    "other": "#8e9186",
}

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY")
)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


def money(value: Decimal | int | float | str) -> str:
    return f"{Decimal(value):,.2f}"


templates.env.filters["money"] = money


def naira(value: Decimal | int | float | str) -> str:
    amount = Decimal(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}₦{abs(amount):,.2f}"


templates.env.filters["naira"] = naira


def current_user_id(request: Request, db: Session) -> int | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None

    user = db.get(User, user_id)
    if user is None:
        request.session.clear()
        return None
    return user.id


def month_bounds(month: date) -> tuple[date, date]:
    start = month.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def parse_money_amount(value: str) -> Decimal:
    value = value.strip()
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?", value):
        raise HTTPException(
            status_code=400,
            detail="Enter a valid amount, using commas only as thousands separators.",
        )
    amount = Decimal(value.replace(",", ""))
    if amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Amount must be greater than zero.",
        )
    return amount


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={}
    )


@app.post("/register")
def register_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    name = name.strip()
    email = email.strip().lower()

    def render_error(error: str):
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "error": error,
                "name": name,
                "email": email
            },
            status_code=400
        )

    if len(password) < 6:
        return render_error("Password must be at least 6 characters.")

    if password != confirm_password:
        return render_error("Passwords do not match.")

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        return render_error("An account with that email already exists.")

    if not EMAIL_PATTERN.fullmatch(email):
        return render_error("Enter a valid email address.")

    password_hash = bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    user = User(full_name=name, email=email, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )


@app.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    email = email.strip().lower()

    def render_error(error: str):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": error,
                "email": email
            },
            status_code=400
        )

    user = db.query(User).filter(User.email == email).first()

    if not user or not bcrypt.checkpw(
        password.encode("utf-8"), user.password_hash.encode("utf-8")
    ):
        return render_error("Incorrect email or password.")

    request.session.clear()
    request.session["user_id"] = user.id

    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/dashboard")
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    user_id = current_user_id(request, db)
    today = date.today()
    month_start, next_month = month_bounds(today)
    expenses = (
        db.query(Expense).filter(Expense.user_id == user_id).all()
        if user_id is not None
        else []
    )
    today_total = sum(
        (expense.amount for expense in expenses if expense.expense_date == today),
        Decimal("0"),
    )
    week_start = today - timedelta(days=today.weekday())
    week_total = sum(
        (
            expense.amount
            for expense in expenses
            if week_start <= expense.expense_date <= today
        ),
        Decimal("0"),
    )
    month_expenses = [
        expense
        for expense in expenses
        if month_start <= expense.expense_date < next_month
    ]
    month_total = sum(
        (expense.amount for expense in month_expenses), Decimal("0")
    )
    category_totals = {
        category: sum(
            (
                expense.amount
                for expense in month_expenses
                if expense.category == category
            ),
            Decimal("0"),
        )
        for category in EXPENSE_CATEGORIES
    }
    category_segments = []
    cumulative = Decimal("0")
    for category, amount in category_totals.items():
        if amount <= 0:
            continue
        start = (cumulative * 100 / month_total).quantize(Decimal("0.01"))
        cumulative += amount
        end = (
            Decimal("100")
            if cumulative == month_total
            else (cumulative * 100 / month_total).quantize(Decimal("0.01"))
        )
        category_segments.append(
            {
                "name": category.title(),
                "category": category,
                "amount": amount,
                "color": CATEGORY_COLORS[category],
                "start": start,
                "end": end,
            }
        )

    daily_totals: dict[str, dict[str, Decimal]] = {}
    for expense in expenses:
        day = daily_totals.setdefault(expense.expense_date.isoformat(), {})
        day[expense.category] = day.get(expense.category, Decimal("0")) + expense.amount
    daily_data = {
        day: [
            {
                "name": category.title(),
                "color": CATEGORY_COLORS[category],
                "amount": str(amount),
            }
            for category, amount in categories.items()
            if category in CATEGORY_COLORS and amount > 0
        ]
        for day, categories in daily_totals.items()
    }

    overall_budget = (
        db.query(Budget)
        .filter(
            Budget.user_id == user_id,
            Budget.budget_type == "overall",
            Budget.month == month_start,
        )
        .first()
        if user_id is not None
        else None
    )
    budget_amount = overall_budget.amount if overall_budget else Decimal("0")
    budgeted_spend = month_total if overall_budget else Decimal("0")
    recent_expenses = sorted(
        expenses,
        key=lambda expense: (expense.expense_date, expense.id),
        reverse=True,
    )[:5]
    budget_progress = (
        budgeted_spend * 100 / budget_amount
        if budget_amount > 0
        else Decimal("0")
    )
    budget_bar_width = min(budget_progress, Decimal("100"))
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "today": today.isoformat(),
            "spent_today": today_total,
            "spent_week": week_total,
            "spent_month": month_total,
            "budgeted_spend": budgeted_spend,
            "has_overall_budget": overall_budget is not None,
            "category_segments": category_segments,
            "daily_data": daily_data,
            "today_iso": today.isoformat(),
            "chart_segments": [
                {
                    "color": segment["color"],
                    "start": str(segment["start"]),
                    "end": str(segment["end"]),
                }
                for segment in category_segments
            ],
            "monthly_budget": budget_amount,
            "budget_progress": budget_progress,
            "budget_bar_width": budget_bar_width,
            "recent_expenses": recent_expenses,
        },
    )


@app.get("/add-expense")
def add_expense_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="add_expenses.html",
        context={"today": date.today().isoformat()}
    )


@app.post("/add-expense")
def add_expense_submit(
    request: Request,
    amount: str = Form(...),
    category: str = Form(...),
    expense_type: str = Form(...),
    spent_at: date = Form(...),
    note: str = Form(""),
    next: str = Form(""),
    db: Session = Depends(get_db),
):
    user_id = current_user_id(request, db)
    if user_id is None:
        return RedirectResponse(url="/login", status_code=303)
    if spent_at > date.today():
        raise HTTPException(
            status_code=400,
            detail="Expenses cannot be dated in the future.",
        )
    amount_value = parse_money_amount(amount)
    if category not in EXPENSE_CATEGORIES:
        raise HTTPException(
            status_code=400, detail="Choose a valid expense category.")
    if expense_type not in ("need", "want"):
        raise HTTPException(status_code=400, detail="Choose need or want.")
    if category == "other" and not note.strip():
        raise HTTPException(
            status_code=400, detail="Tell us what kind of expense this was.")

    expense = Expense(
        user_id=user_id,
        amount=amount_value,
        category=category,
        expense_type=expense_type,
        note=note.strip() or None,
        expense_date=spent_at,
    )
    db.add(expense)
    db.commit()
    return RedirectResponse(
        url="/dashboard" if next == "dashboard" else "/transactions",
        status_code=303,
    )


@app.get("/transactions")
def transactions_page(
    request: Request,
    search: str = "",
    category: str = "",
    expense_type: str = "",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        start_date_value = (
            date.fromisoformat(start_date.strip())
            if start_date and start_date.strip()
            else None
        )
        end_date_value = (
            date.fromisoformat(end_date.strip())
            if end_date and end_date.strip()
            else None
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail="Enter valid start and end dates.",
        ) from error

    user_id = current_user_id(request, db)
    query = db.query(Expense)
    if user_id is None:
        query = query.filter(Expense.id == -1)
    else:
        query = query.filter(Expense.user_id == user_id)
    if search.strip():
        query = query.filter(Expense.note.ilike(f"%{search.strip()}%"))
    if category and category not in EXPENSE_CATEGORIES:
        raise HTTPException(
            status_code=400, detail="Choose a valid category filter.")
    if category:
        query = query.filter(Expense.category == category)
    if expense_type and expense_type not in ("need", "want"):
        raise HTTPException(
            status_code=400, detail="Choose a valid type filter.")
    if expense_type:
        query = query.filter(Expense.expense_type == expense_type)
    if (
        start_date_value
        and end_date_value
        and start_date_value > end_date_value
    ):
        raise HTTPException(
            status_code=400,
            detail="The start date must be on or before the end date.",
        )
    if start_date_value:
        query = query.filter(Expense.expense_date >= start_date_value)
    if end_date_value:
        query = query.filter(Expense.expense_date <= end_date_value)

    expenses = query.order_by(
        Expense.expense_date.desc(), Expense.id.desc()
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="transactions.html",
        context={
            "expenses": expenses,
            "search": search,
            "category": category,
            "expense_type": expense_type,
            "start_date": start_date_value,
            "end_date": end_date_value,
        },
    )


@app.get("/budgets")
def budgets_page(
    request: Request,
    month: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        selected_month = (
            datetime.strptime(month, "%Y-%m").date()
            if month
            else date.today()
        ).replace(day=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Choose a valid month.")

    month_start, next_month = month_bounds(selected_month)
    user_id = current_user_id(request, db)
    budgets = (
        db.query(Budget)
        .filter(Budget.user_id == user_id, Budget.month == month_start)
        .all()
        if user_id is not None
        else []
    )
    expenses = (
        db.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.expense_date >= month_start,
            Expense.expense_date < next_month,
        )
        .all()
        if user_id is not None
        else []
    )
    overall_budget = next(
        (budget for budget in budgets if budget.budget_type == "overall"),
        None,
    )
    budget_amount = overall_budget.amount if overall_budget else Decimal("0")
    tracked_spent = sum((expense.amount for expense in expenses), Decimal("0"))
    overall_progress = (
        tracked_spent * 100 / budget_amount
        if budget_amount > 0
        else Decimal("0")
    )
    return templates.TemplateResponse(
        request=request,
        name="budgets.html",
        context={
            "selected_month": selected_month.strftime("%Y-%m"),
            "budget_amount": budget_amount,
            "spent": tracked_spent,
            "remaining": budget_amount - tracked_spent,
            "overall_progress": overall_progress,
            "overall_budget": overall_budget,
        },
    )


@app.post("/budgets")
def budget_submit(
    request: Request,
    category: str = Form(""),
    amount: str = Form(...),
    month: str = Form(...),
    db: Session = Depends(get_db),
):
    user_id = current_user_id(request, db)
    if user_id is None:
        return RedirectResponse(url="/login", status_code=303)
    if category and category not in EXPENSE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Choose a valid category.")
    amount_value = parse_money_amount(amount)

    try:
        month_start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Choose a valid month.")

    budget_category = category or None
    budget = (
        db.query(Budget)
        .filter(
            Budget.user_id == user_id,
            Budget.budget_type == "overall",
            Budget.month == month_start,
        )
        .first()
    )

    if budget is None:
        budget = Budget(
            user_id=user_id,
            budget_type="overall",
            category=budget_category,
            amount=amount_value,
            month=month_start,
        )
        db.add(budget)
    else:
        budget.amount = amount_value
        budget.category = budget_category

    db.commit()
    return RedirectResponse(
        url=f"/budgets?month={month_start:%Y-%m}",
        status_code=303,
    )


@app.post("/budgets/{budget_id}/edit")
def budget_edit(
    budget_id: int,
    request: Request,
    category: str = Form(""),
    amount: str = Form(...),
    month: str = Form(...),
    db: Session = Depends(get_db),
):
    user_id = current_user_id(request, db)
    if user_id is None:
        return RedirectResponse(url="/login", status_code=303)

    budget = (
        db.query(Budget)
        .filter(Budget.id == budget_id, Budget.user_id == user_id)
        .first()
    )
    if budget is None:
        raise HTTPException(status_code=404, detail="Budget not found.")
    if category and category not in EXPENSE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Choose a valid category.")

    amount_value = parse_money_amount(amount)

    try:
        month_start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Choose a valid month.")

    budget_category = category or None
    duplicate = (
        db.query(Budget)
        .filter(
            Budget.user_id == user_id,
            Budget.budget_type == "overall",
            Budget.month == month_start,
            Budget.id != budget.id,
        )
        .first()
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=400,
            detail="A budget already exists for this month.",
        )

    budget.budget_type = "overall"
    budget.category = budget_category
    budget.amount = amount_value
    budget.month = month_start
    db.commit()
    return RedirectResponse(
        url=f"/budgets?month={month_start:%Y-%m}",
        status_code=303,
    )
