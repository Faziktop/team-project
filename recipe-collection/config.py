import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Security: Read secret key from environment or fallback to robust development default
    SECRET_KEY = os.environ.get('SECRET_KEY', 'recipe-hub-super-secret-key-prod-secure-2026')
    
    # Database: SQLite in instance folder by default, configurable for PostgreSQL/MySQL
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 
        f"sqlite:///{os.path.join(basedir, 'instance', 'recipes.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File uploads
    UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    # Pagination
    RECIPES_PER_PAGE = 9
    
    # Culinary taxonomies
    CATEGORIES = [
        "Завтраки",
        "Основные блюда",
        "Супы",
        "Салаты",
        "Десерты и выпечка",
        "Закуски",
        "Напитки",
        "Соусы и маринады"
    ]
    
    CUISINES = [
        "Итальянская",
        "Русская",
        "Грузинская",
        "Французская",
        "Паназиатская",
        "Японская",
        "Мексиканская",
        "Средиземноморская",
        "Американская",
        "Ближневосточная",
        "Другая"
    ]
    
    DIFFICULTIES = [
        "Легко",
        "Средне",
        "Сложно"
    ]
