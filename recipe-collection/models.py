from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import re

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    bio = db.Column(db.Text, default='')
    avatar = db.Column(db.String(256), default='')
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    recipes = db.relationship('Recipe', backref='author', lazy=True, cascade='all, delete-orphan')
    reviews = db.relationship('Review', backref='author', lazy=True, cascade='all, delete-orphan')
    favorites = db.relationship('Favorite', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_avatar_url(self):
        if self.avatar:
            return f"/uploads/{self.avatar}"
        # Fallback to high-resolution UI-Avatars service
        return f"https://ui-avatars.com/api/?name={self.username}&background=FF6B4A&color=fff&size=128&bold=true"

    def has_favorited(self, recipe_id):
        return any(fav.recipe_id == recipe_id for fav in self.favorites)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'bio': self.bio,
            'is_admin': self.is_admin,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'recipes_count': len(self.recipes),
            'favorites_count': len(self.favorites)
        }


class Recipe(db.Model):
    __tablename__ = 'recipe'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    cuisine = db.Column(db.String(100), nullable=False, index=True)
    category = db.Column(db.String(100), nullable=False, default='Основные блюда', index=True)
    difficulty = db.Column(db.String(50), nullable=False, default='Средне')
    prep_time = db.Column(db.Integer, nullable=False, default=15)  # minutes
    cook_time = db.Column(db.Integer, nullable=False, default=30)  # minutes
    servings = db.Column(db.Integer, nullable=False, default=4)
    calories = db.Column(db.Integer, nullable=True)   # kcal per serving
    protein = db.Column(db.Float, nullable=True)     # grams
    fat = db.Column(db.Float, nullable=True)         # grams
    carbs = db.Column(db.Float, nullable=True)       # grams
    dietary = db.Column(db.String(200), default='')  # tags: e.g. "Вегетарианское, ПП"
    description = db.Column(db.Text, nullable=False)
    ingredients = db.Column(db.Text, nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    images = db.Column(db.Text, default='')          # comma separated filenames
    views_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Relationships
    reviews = db.relationship('Review', backref='recipe', lazy=True, cascade='all, delete-orphan')
    favorites = db.relationship('Favorite', backref='recipe', lazy=True, cascade='all, delete-orphan')

    @property
    def total_time(self):
        return (self.prep_time or 0) + (self.cook_time or 0)

    @property
    def total_time_formatted(self):
        minutes = self.total_time
        if minutes < 60:
            return f"{minutes} мин"
        hours = minutes // 60
        rem_min = minutes % 60
        if rem_min == 0:
            return f"{hours} ч"
        return f"{hours} ч {rem_min} мин"

    @property
    def average_rating(self):
        if not self.reviews:
            return 0.0
        return round(sum(r.rating for r in self.reviews) / len(self.reviews), 1)

    @property
    def reviews_count(self):
        return len(self.reviews)

    @property
    def favorites_count(self):
        return len(self.favorites)

    def get_images(self):
        if self.images:
            return [img.strip() for img in self.images.split(',') if img.strip()]
        return []

    def get_main_image(self):
        images = self.get_images()
        return images[0] if images else None

    def get_main_image_url(self):
        main_img = self.get_main_image()
        if main_img:
            return f"/uploads/{main_img}"
        return "/static/img/placeholder.svg"

    def dietary_list(self):
        if self.dietary:
            return [tag.strip() for tag in self.dietary.split(',') if tag.strip()]
        return []

    def parsed_ingredients(self):
        """
        Parses ingredients into structured objects for automatic serving scaling.
        Handles formats like:
        '400 г спагетти' -> amount=400, unit='г', name='спагетти'
        '2 яйца' -> amount=2, unit='', name='яйца'
        'Соль по вкусу' -> amount=None, unit='', name='Соль по вкусу'
        """
        results = []
        pattern = re.compile(r'^\s*(?:[-*•]\s*)?([\d.,/]+)?\s*([a-zA-Zа-яА-ЯёЁ.]+(?:\s+[a-zA-Zа-яА-ЯёЁ.]+)*?)?\s*[-:]?\s*(.+)$')
        # Common culinary units
        units_set = {'г', 'гр', 'кг', 'мл', 'л', 'ч.л.', 'ч. л.', 'ст.л.', 'ст. л.', 'шт', 'шт.', 'зубчик', 'зубчика', 'зубчиков', 'щепотка', 'стакан', 'стакана', 'пучок', 'бан.'}

        for line in self.ingredients.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Simple heuristic regex for leading number and unit
            m = re.match(r'^\s*(?:[-*•]\s*)?([\d.,]+)\s*([a-zA-Zа-яА-ЯёЁ.]+)?\s*(.*)$', line)
            if m:
                raw_amt, potential_unit, rest = m.groups()
                try:
                    amt = float(raw_amt.replace(',', '.'))
                except ValueError:
                    amt = None
                
                potential_unit = (potential_unit or '').strip().lower()
                rest = (rest or '').strip()

                if potential_unit in units_set:
                    unit = potential_unit
                    name = rest
                elif potential_unit and not rest:
                    unit = ''
                    name = potential_unit
                else:
                    unit = ''
                    name = f"{potential_unit} {rest}".strip()

                results.append({
                    'raw': line,
                    'amount': amt,
                    'unit': unit,
                    'name': name or line
                })
            else:
                results.append({
                    'raw': line,
                    'amount': None,
                    'unit': '',
                    'name': line
                })
        return results

    def parsed_instructions(self):
        """
        Splits instruction text into structured steps with detected timers.
        """
        steps = []
        raw_lines = self.instructions.strip().split('\n')
        current_step = 1
        timer_pattern = re.compile(r'(\d+)\s*(?:-|–|\s+до\s+)?(\d+)?\s*(минут|мин|минуты|минута|секунд|сек|часов|часа|час)', re.IGNORECASE)

        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            
            # Strip leading step numbers like '1.', 'Шаг 1:', etc.
            clean_text = re.sub(r'^(?:шаг\s*)?\d+[\.:\)]\s*', '', line, flags=re.IGNORECASE).strip()
            if not clean_text:
                clean_text = line

            # Check for timer mentions
            detected_seconds = 0
            m = timer_pattern.search(clean_text)
            if m:
                val1 = int(m.group(1))
                val2 = int(m.group(2)) if m.group(2) else val1
                unit = m.group(3).lower()
                avg_val = (val1 + val2) // 2
                
                if 'час' in unit:
                    detected_seconds = avg_val * 3600
                elif 'мин' in unit:
                    detected_seconds = avg_val * 60
                elif 'сек' in unit:
                    detected_seconds = avg_val

            steps.append({
                'number': current_step,
                'text': clean_text,
                'timer_seconds': detected_seconds,
                'timer_label': m.group(0) if m else None
            })
            current_step += 1

        return steps

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'cuisine': self.cuisine,
            'category': self.category,
            'difficulty': self.difficulty,
            'prep_time': self.prep_time,
            'cook_time': self.cook_time,
            'total_time': self.total_time,
            'total_time_formatted': self.total_time_formatted,
            'servings': self.servings,
            'calories': self.calories,
            'protein': self.protein,
            'fat': self.fat,
            'carbs': self.carbs,
            'dietary': self.dietary_list(),
            'description': self.description,
            'ingredients': self.ingredients,
            'instructions': self.instructions,
            'images': self.get_images(),
            'main_image_url': self.get_main_image_url(),
            'views_count': self.views_count,
            'rating': self.average_rating,
            'reviews_count': self.reviews_count,
            'favorites_count': self.favorites_count,
            'author': {
                'id': self.author.id,
                'username': self.author.username
            },
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Review(db.Model):
    __tablename__ = 'review'
    
    id = db.Column(db.Integer, primary_key=True)
    rating = db.Column(db.Integer, nullable=False)  # 1 to 5
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'rating': self.rating,
            'comment': self.comment,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'user': {
                'id': self.author.id,
                'username': self.author.username,
                'avatar': self.author.get_avatar_url()
            }
        }


class Favorite(db.Model):
    __tablename__ = 'favorite'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'recipe_id', name='_user_recipe_fav_uc'),
    )
