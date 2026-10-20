from datetime import date, datetime, timedelta
from decimal import Decimal

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

app.add_middleware(
    SessionMiddleware,
    secret_key="local-development-secret-change-before-launch"
)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


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

    password_hash = bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    user = User(full_name=name, email=email, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)

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
    wants_total = sum(
        (
            expense.amount
            for expense in month_expenses
            if expense.expense_type == "want"
        ),
        Decimal("0"),
    )
    budget = (
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
    recent_expenses = sorted(
        expenses,
        key=lambda expense: (expense.expense_date, expense.id),
        reverse=True,
    )[:5]
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "spent_today": today_total,
            "spent_week": week_total,
            "spent_month": month_total,
            "wants_month": wants_total,
            "monthly_budget": budget.amount if budget else Decimal("0"),
            "recent_expenses": recent_expenses,
        },
    )


@app.get("/add-expense")
def add_expense_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="add_expenses.html",
        context={}
    )


@app.post("/add-expense")
def add_expense_submit(
    request: Request,
    amount: Decimal = Form(...),
    category: str = Form(...),
    expense_type: str = Form(...),
    spent_at: date = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    user_id = current_user_id(request, db)
    if user_id is None:
        return RedirectResponse(url="/login", status_code=303)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")
    if category not in EXPENSE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Choose a valid expense category.")
    if expense_type not in ("need", "want"):
        raise HTTPException(status_code=400, detail="Choose need or want.")

    expense = Expense(
        user_id=user_id,
        amount=amount,
        category=category,
        expense_type=expense_type,
        note=note.strip() or None,
        expense_date=spent_at,
    )
    db.add(expense)
    db.commit()
    return RedirectResponse(url="/transactions", status_code=303)


@app.get("/transactions")
def transactions_page(
    request: Request,
    search: str = "",
    category: str = "",
    expense_type: str = "",
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    user_id = current_user_id(request, db)
    query = db.query(Expense)
    if user_id is None:
        query = query.filter(Expense.id == -1)
    else:
        query = query.filter(Expense.user_id == user_id)
    if search.strip():
        query = query.filter(Expense.note.ilike(f"%{search.strip()}%"))
    if category in EXPENSE_CATEGORIES:
        query = query.filter(Expense.category == category)
    if expense_type in ("need", "want"):
        query = query.filter(Expense.expense_type == expense_type)
    if start_date:
        query = query.filter(Expense.expense_date >= start_date)
    if end_date:
        query = query.filter(Expense.expense_date <= end_date)

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
            "start_date": start_date,
            "end_date": end_date,
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
    category_budgets = [
        budget for budget in budgets if budget.budget_type == "category"
    ]
    spent = sum((expense.amount for expense in expenses), Decimal("0"))
    budget_amount = overall_budget.amount if overall_budget else Decimal("0")
    category_spending = {
        category: sum(
            (
                expense.amount
                for expense in expenses
                if expense.category == category
            ),
            Decimal("0"),
        )
        for category in EXPENSE_CATEGORIES
    }
    return templates.TemplateResponse(
        request=request,
        name="budgets.html",
        context={
            "selected_month": selected_month.strftime("%Y-%m"),
            "budget_amount": budget_amount,
            "spent": spent,
            "remaining": budget_amount - spent,
            "overall_budget": overall_budget,
            "category_budgets": category_budgets,
            "category_spending": category_spending,
        },
    )


@app.post("/budgets")
def budget_submit(
    request: Request,
    budget_type: str = Form(...),
    category: str = Form(""),
    amount: Decimal = Form(...),
    month: str = Form(...),
    db: Session = Depends(get_db),
):
    user_id = current_user_id(request, db)
    if user_id is None:
        return RedirectResponse(url="/login", status_code=303)
    if budget_type not in ("overall", "category"):
        raise HTTPException(status_code=400, detail="Choose a valid budget type.")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")
    if budget_type == "category" and category not in EXPENSE_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail="Choose a category for a category budget.",
        )

    try:
        month_start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Choose a valid month.")

    budget_category = category if budget_type == "category" else None
    budget_query = db.query(Budget).filter(
        Budget.user_id == user_id,
        Budget.budget_type == budget_type,
        Budget.month == month_start,
    )
    if budget_category is None:
        budget_query = budget_query.filter(Budget.category.is_(None))
    else:
        budget_query = budget_query.filter(Budget.category == budget_category)
    budget = budget_query.first()

    if budget is None:
        budget = Budget(
            user_id=user_id,
            budget_type=budget_type,
            category=budget_category,
            amount=amount,
            month=month_start,
        )
        db.add(budget)
    else:
        budget.amount = amount

    db.commit()
    return RedirectResponse(
        url=f"/budgets?month={month_start:%Y-%m}",
        status_code=303,
    )
