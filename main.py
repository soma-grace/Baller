import bcrypt
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from database import Base, engine, get_db
from models import User
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Baller")

app.add_middleware(
    SessionMiddleware,
    secret_key="local-development-secret-change-before-launch"
)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")


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
def dashboard_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={}
    )


@app.get("/add-expense")
def add_expense_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="add_expenses.html",
        context={}
    )


@app.get("/transactions")
def transactions_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="transactions.html",
        context={}
    )


@app.get("/budgets")
def budgets_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="budgets.html",
        context={}
    )
