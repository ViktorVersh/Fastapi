from fastapi import FastAPI, Form, Depends, Request, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
# from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")
# app.mount("/static", StaticFiles(directory="static"), name="static")

# Настройка SQLAlchemy
DATABASE_URL = "sqlite:///./fastapdb.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Настройка для хэширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Модель пользователя
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    tasks = relationship("Task", back_populates="user")


# Модель задачи
class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)
    category = Column(String)
    data_created = Column(DateTime)
    data_end_plan = Column(DateTime)
    status = Column(String)
    data_end = Column(DateTime)
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="tasks")


Base.metadata.create_all(bind=engine)


# Pydantic модели
class TaskForm(BaseModel):
    name: str
    description: str
    category: str
    data_end_plan: datetime
    status: str


class FilterForm(BaseModel):
    date: Optional[datetime] = None
    name: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None


# Вспомогательные функции
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


# Маршруты
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...),
                db: SessionLocal = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid username or password")
    response = RedirectResponse(url="/dashboard", status_code=303)
    request.session["user_id"] = user.id
    return response


@app.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
async def register(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        db: SessionLocal = Depends(get_db)
):
    # Проверяем, существует ли пользователь с таким именем
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Хэшируем пароль
    hashed_password = get_password_hash(password)

    # Создаем нового пользователя
    new_user = User(username=username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Перенаправляем на страницу входа
    return RedirectResponse(url="/", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: SessionLocal = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)

    tasks = db.query(Task).filter(Task.user_id == user_id).all()

    # Рассчитываем статистику
    total_tasks = len(tasks)
    completed_tasks = len([task for task in tasks if task.status == "Completed"])
    pending_tasks = total_tasks - completed_tasks

    statistics = {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "pending_tasks": pending_tasks,
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "tasks": tasks, "statistics": statistics}
    )


@app.get("/add-task", response_class=HTMLResponse)
async def add_task_get(request: Request):
    """
    Маршрут для отображения страницы добавления задачи.
    """
    return templates.TemplateResponse("add_task.html", {"request": request})


@app.post("/add-task")
async def add_task_post(
        request: Request,
        name: str = Form(...),
        description: str = Form(...),
        category: str = Form(...),
        data_end_plan: datetime = Form(...),
        status: str = Form(...),
        db: SessionLocal = Depends(get_db)
):
    """
    Маршрут для добавления задачи в базу данных.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    new_task = Task(
        name=name,
        description=description,
        category=category,
        data_created=datetime.now(),
        data_end_plan=data_end_plan,
        status=status,
        user_id=user_id  # Привязываем задачу к текущему пользователю
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/edit-task/{task_id}", response_class=HTMLResponse)
async def edit_task_get(request: Request, task_id: int, db: SessionLocal = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return templates.TemplateResponse("edit_task.html", {"request": request, "task": task})


@app.post("/edit-task/{task_id}")
async def edit_task_post(
        request: Request,
        task_id: int,
        name: str = Form(...),
        description: str = Form(...),
        category: str = Form(...),
        data_end_plan: str = Form(...),  # Получаем как строку
        status: str = Form(...),
        db: SessionLocal = Depends(get_db)
):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Преобразуем строку в datetime
    data_end_plan_obj = datetime.strptime(data_end_plan, "%Y-%m-%dT%H:%M")

    task.name = name
    task.description = description
    task.category = category
    task.data_end_plan = data_end_plan_obj
    task.status = status

    db.commit()
    db.refresh(task)
    return RedirectResponse(url="/dashboard", status_code=303)


@app.post("/delete-task/{task_id}")
async def delete_task(task_id: int, db: SessionLocal = Depends(get_db)):
    """
    Маршрут для удаления задачи из базы данных.
    :param task_id:
    :param db:
    :return:
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    """
    Маршрут для выхода из системы.
    """
    if "user_id" in request.session:
        del request.session["user_id"]
    return RedirectResponse(url="/", status_code=303)



@app.post("/filter-tasks")
async def filter_tasks(
        request: Request,
        filter_data: FilterForm = Depends(),
        db: SessionLocal = Depends(get_db)
):
    """
    Маршрут для перехода к фильтрации задач в базе данных.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    query = db.query(Task).filter(Task.user_id == user_id)

    if filter_data.date:
        query = query.filter(Task.data_created == filter_data.date)

    if filter_data.name:
        query = query.filter(Task.name.ilike(f"%{filter_data.name}%"))

    if filter_data.status:
        query = query.filter(Task.status == filter_data.status)

    if filter_data.priority:
        query = query.filter(Task.priority == filter_data.priority)

    tasks = query.all()
    return {"tasks": [{"name": task.name, "status": task.status} for task in tasks]}


@app.get("/filter-tasks", response_class=HTMLResponse)
async def filter_tasks(
        request: Request,
        date: Optional[str] = Query(None),
        name: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        priority: Optional[str] = Query(None),
        db: SessionLocal = Depends(get_db)
):
    """
    Маршрут для фильтрации задач в базе данных.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)

    query = db.query(Task).filter(Task.user_id == user_id)

    if date:
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        next_day = date_obj + timedelta(days=1)
        query = query.filter(Task.data_created >= date_obj, Task.data_created < next_day)

    if name:
        query = query.filter(Task.name.ilike(f"%{name}%"))

    if status:
        query = query.filter(Task.status == status)

    if priority:
        query = query.filter(Task.priority == priority)

    tasks = query.all()

    # Рассчитываем статистику
    total_tasks = len(tasks)
    completed_tasks = len([task for task in tasks if task.status == "Completed"])
    in_progress_tasks = len([task for task in tasks if task.status == "In Progress"])
    planned_tasks = len([task for task in tasks if task.status == "Planned"])

    statistics = {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "in_progress_tasks": in_progress_tasks,
        "planned_tasks": planned_tasks,
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "tasks": tasks, "statistics": statistics}
    )


# Запуск приложения
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
