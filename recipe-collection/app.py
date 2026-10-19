from flask import (
    Flask, render_template, request, redirect, url_for, flash, 
    abort, send_from_directory, jsonify
)
from flask_login import (
    LoginManager, login_user, login_required, logout_user, current_user
)
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import uuid
from functools import wraps

from config import Config
from models import db, User, Recipe, Review, Favorite

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure upload folder and instance folder exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    instance_dir = os.path.join(app.root_path, 'instance')
    os.makedirs(instance_dir, exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Пожалуйста, войдите в систему для доступа к этой странице.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Helper functions
    def allowed_file(filename):
        return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

    def generate_filename(filename):
        ext = filename.rsplit('.', 1)[1].lower()
        return f"{uuid.uuid4().hex}.{ext}"

    def admin_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_admin:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function

    # Context Processors for Templates
    @app.context_processor
    def inject_global_data():
        user_favs_count = 0
        if current_user.is_authenticated:
            user_favs_count = Favorite.query.filter_by(user_id=current_user.id).count()
        return {
            'app_categories': app.config['CATEGORIES'],
            'app_cuisines': app.config['CUISINES'],
            'app_difficulties': app.config['DIFFICULTIES'],
            'user_favorites_count': user_favs_count,
            'current_year': datetime.utcnow().year
        }

    # Static uploads handler
    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    # ==================== MAIN CATALOG & SEARCH ====================
    @app.route('/')
    def index():
        search_query = request.args.get('q', '').strip()
        cuisine = request.args.get('cuisine', '').strip()
        category = request.args.get('category', '').strip()
        difficulty = request.args.get('difficulty', '').strip()
        max_time = request.args.get('max_time', type=int)
        sort_by = request.args.get('sort', 'newest')
        page = request.args.get('page', 1, type=int)

        query = Recipe.query

        # Search filter across title, description, cuisine, ingredients
        if search_query:
            search_pattern = f"%{search_query}%"
            query = query.filter(
                (Recipe.title.ilike(search_pattern)) |
                (Recipe.description.ilike(search_pattern)) |
                (Recipe.cuisine.ilike(search_pattern)) |
                (Recipe.ingredients.ilike(search_pattern))
            )

        # Categorical filters
        if cuisine:
            query = query.filter(Recipe.cuisine == cuisine)
        if category and category != 'Все':
            query = query.filter(Recipe.category == category)
        if difficulty:
            query = query.filter(Recipe.difficulty == difficulty)
        if max_time:
            query = query.filter((Recipe.prep_time + Recipe.cook_time) <= max_time)

        # Sorting
        if sort_by == 'popular':
            query = query.order_by(Recipe.views_count.desc(), Recipe.created_at.desc())
        elif sort_by == 'fastest':
            query = query.order_by((Recipe.prep_time + Recipe.cook_time).asc())
        elif sort_by == 'oldest':
            query = query.order_by(Recipe.created_at.asc())
        else:  # newest default
            query = query.order_by(Recipe.created_at.desc())

        pagination = query.paginate(page=page, per_page=app.config['RECIPES_PER_PAGE'], error_out=False)
        recipes = pagination.items

        # Quick stats for hero banner
        total_recipes_count = Recipe.query.count()

        return render_template(
            'index.html',
            recipes=recipes,
            pagination=pagination,
            search_query=search_query,
            selected_cuisine=cuisine,
            selected_category=category,
            selected_difficulty=difficulty,
            selected_max_time=max_time,
            selected_sort=sort_by,
            total_recipes_count=total_recipes_count
        )

    # ==================== RECIPE DETAILS & COOKING MODE ====================
    @app.route('/recipe/<int:recipe_id>')
    def recipe_detail(recipe_id):
        recipe = Recipe.query.get_or_404(recipe_id)
        
        # Increment views counter
        recipe.views_count += 1
        db.session.commit()

        # Check if user already reviewed
        user_review = None
        is_favorite = False
        if current_user.is_authenticated:
            user_review = Review.query.filter_by(recipe_id=recipe.id, user_id=current_user.id).first()
            is_favorite = current_user.has_favorited(recipe.id)

        # Related recipes from same cuisine or category
        related_recipes = Recipe.query.filter(
            (Recipe.cuisine == recipe.cuisine) | (Recipe.category == recipe.category),
            Recipe.id != recipe.id
        ).order_by(Recipe.views_count.desc()).limit(3).all()

        return render_template(
            'recipe_detail.html',
            recipe=recipe,
            ingredients=recipe.parsed_ingredients(),
            instructions=recipe.parsed_instructions(),
            images=recipe.get_images(),
            user_review=user_review,
            is_favorite=is_favorite,
            related_recipes=related_recipes
        )

    @app.route('/recipe/<int:recipe_id>/cook')
    def cooking_mode(recipe_id):
        recipe = Recipe.query.get_or_404(recipe_id)
        return render_template(
            'cooking_mode.html',
            recipe=recipe,
            instructions=recipe.parsed_instructions(),
            ingredients=recipe.parsed_ingredients()
        )

    # ==================== RECIPE CRUD ====================
    @app.route('/recipe/add', methods=['GET', 'POST'])
    @login_required
    def add_recipe():
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            cuisine = request.form.get('cuisine', '').strip()
            category = request.form.get('category', 'Основные блюда').strip()
            difficulty = request.form.get('difficulty', 'Средне').strip()
            prep_time = request.form.get('prep_time', type=int) or 15
            cook_time = request.form.get('cook_time', type=int) or 30
            servings = request.form.get('servings', type=int) or 4
            calories = request.form.get('calories', type=int)
            protein = request.form.get('protein', type=float)
            fat = request.form.get('fat', type=float)
            carbs = request.form.get('carbs', type=float)
            dietary = request.form.get('dietary', '').strip()
            description = request.form.get('description', '').strip()
            ingredients = request.form.get('ingredients', '').strip()
            instructions = request.form.get('instructions', '').strip()

            if not title or not cuisine or not description or not ingredients or not instructions:
                flash('Пожалуйста, заполните все обязательные поля!', 'error')
                return render_template('add_recipe.html', form_data=request.form)

            # Process image uploads
            image_paths = []
            if 'images' in request.files:
                files = request.files.getlist('images')
                for file in files:
                    if file and file.filename != '' and allowed_file(file.filename):
                        safe_name = secure_filename(file.filename)
                        unique_name = generate_filename(safe_name)
                        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
                        image_paths.append(unique_name)

            recipe = Recipe(
                title=title,
                cuisine=cuisine,
                category=category,
                difficulty=difficulty,
                prep_time=prep_time,
                cook_time=cook_time,
                servings=servings,
                calories=calories,
                protein=protein,
                fat=fat,
                carbs=carbs,
                dietary=dietary,
                description=description,
                ingredients=ingredients,
                instructions=instructions,
                images=','.join(image_paths),
                user_id=current_user.id
            )

            db.session.add(recipe)
            db.session.commit()
            flash('Рецепт успешно добавлен в коллекцию!', 'success')
            return redirect(url_for('recipe_detail', recipe_id=recipe.id))

        return render_template('add_recipe.html')

    @app.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_recipe(recipe_id):
        recipe = Recipe.query.get_or_404(recipe_id)

        # Check permissions
        if recipe.user_id != current_user.id and not current_user.is_admin:
            abort(403)

        if request.method == 'POST':
            recipe.title = request.form.get('title', '').strip()
            recipe.cuisine = request.form.get('cuisine', '').strip()
            recipe.category = request.form.get('category', 'Основные блюда').strip()
            recipe.difficulty = request.form.get('difficulty', 'Средне').strip()
            recipe.prep_time = request.form.get('prep_time', type=int) or 15
            recipe.cook_time = request.form.get('cook_time', type=int) or 30
            recipe.servings = request.form.get('servings', type=int) or 4
            recipe.calories = request.form.get('calories', type=int)
            recipe.protein = request.form.get('protein', type=float)
            recipe.fat = request.form.get('fat', type=float)
            recipe.carbs = request.form.get('carbs', type=float)
            recipe.dietary = request.form.get('dietary', '').strip()
            recipe.description = request.form.get('description', '').strip()
            recipe.ingredients = request.form.get('ingredients', '').strip()
            recipe.instructions = request.form.get('instructions', '').strip()

            # Handle new image uploads
            if 'images' in request.files:
                files = request.files.getlist('images')
                existing_images = recipe.get_images()
                new_images = []

                for file in files:
                    if file and file.filename != '' and allowed_file(file.filename):
                        safe_name = secure_filename(file.filename)
                        unique_name = generate_filename(safe_name)
                        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
                        new_images.append(unique_name)

                if new_images:
                    recipe.images = ','.join(existing_images + new_images)

            recipe.updated_at = datetime.utcnow()
            db.session.commit()
            flash('Рецепт успешно обновлен!', 'success')
            return redirect(url_for('recipe_detail', recipe_id=recipe.id))

        return render_template('edit_recipe.html', recipe=recipe, images=recipe.get_images())

    @app.route('/recipe/<int:recipe_id>/delete-image/<filename>', methods=['POST'])
    @login_required
    def delete_recipe_image(recipe_id, filename):
        recipe = Recipe.query.get_or_404(recipe_id)

        if recipe.user_id != current_user.id and not current_user.is_admin:
            abort(403)

        images = recipe.get_images()
        if filename in images:
            images.remove(filename)
            recipe.images = ','.join(images)

            # Remove file from disk
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass

            db.session.commit()
            flash('Изображение удалено!', 'success')

        return redirect(url_for('edit_recipe', recipe_id=recipe.id))

    @app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
    @login_required
    def delete_recipe(recipe_id):
        recipe = Recipe.query.get_or_404(recipe_id)

        if recipe.user_id != current_user.id and not current_user.is_admin:
            abort(403)

        # Remove image files
        for filename in recipe.get_images():
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass

        db.session.delete(recipe)
        db.session.commit()
        flash('Рецепт успешно удален!', 'success')

        if request.referrer and 'profile' in request.referrer:
            return redirect(url_for('profile', username=current_user.username))
        return redirect(url_for('index'))

    # ==================== FAVORITES & REVIEWS ====================
    @app.route('/recipe/<int:recipe_id>/favorite', methods=['POST'])
    @login_required
    def toggle_favorite(recipe_id):
        recipe = Recipe.query.get_or_404(recipe_id)
        fav = Favorite.query.filter_by(user_id=current_user.id, recipe_id=recipe.id).first()

        if fav:
            db.session.delete(fav)
            is_fav = False
            msg = 'Рецепт удален из избранного'
        else:
            fav = Favorite(user_id=current_user.id, recipe_id=recipe.id)
            db.session.add(fav)
            is_fav = True
            msg = 'Рецепт добавлен в избранное!'

        db.session.commit()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({
                'status': 'success',
                'is_favorite': is_fav,
                'count': recipe.favorites_count,
                'message': msg
            })

        flash(msg, 'info')
        return redirect(request.referrer or url_for('recipe_detail', recipe_id=recipe_id))

    @app.route('/recipe/<int:recipe_id>/review', methods=['POST'])
    @login_required
    def add_review(recipe_id):
        recipe = Recipe.query.get_or_404(recipe_id)
        rating = request.form.get('rating', type=int)
        comment = request.form.get('comment', '').strip()

        if not rating or rating < 1 or rating > 5:
            flash('Пожалуйста, выберите оценку от 1 до 5 звезд!', 'error')
            return redirect(url_for('recipe_detail', recipe_id=recipe_id))

        # Check if user already reviewed
        review = Review.query.filter_by(recipe_id=recipe.id, user_id=current_user.id).first()
        if review:
            review.rating = rating
            review.comment = comment
            review.created_at = datetime.utcnow()
            flash('Ваш отзыв обновлен!', 'success')
        else:
            review = Review(
                rating=rating,
                comment=comment,
                recipe_id=recipe.id,
                user_id=current_user.id
            )
            db.session.add(review)
            flash('Спасибо за ваш отзыв!', 'success')

        db.session.commit()
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))

    @app.route('/review/<int:review_id>/delete', methods=['POST'])
    @login_required
    def delete_review(review_id):
        review = Review.query.get_or_404(review_id)
        recipe_id = review.recipe_id

        if review.user_id != current_user.id and not current_user.is_admin:
            abort(403)

        db.session.delete(review)
        db.session.commit()
        flash('Отзыв удален!', 'success')
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))

    # ==================== USER PROFILE & SHOPPING LIST ====================
    @app.route('/profile')
    @login_required
    def my_profile():
        return redirect(url_for('profile', username=current_user.username))

    @app.route('/profile/<username>')
    def profile(username):
        user = User.query.filter_by(username=username).first_or_404()
        user_recipes = Recipe.query.filter_by(user_id=user.id).order_by(Recipe.created_at.desc()).all()
        
        # User's favorited recipes
        favorites = []
        if current_user.is_authenticated and current_user.id == user.id:
            favorites = [fav.recipe for fav in user.favorites]

        # Calculate statistics
        total_views = sum(r.views_count for r in user_recipes)
        ratings = [r.average_rating for r in user_recipes if r.average_rating > 0]
        avg_user_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0

        return render_template(
            'profile.html',
            profile_user=user,
            recipes=user_recipes,
            favorites=favorites,
            total_views=total_views,
            avg_rating=avg_user_rating
        )

    @app.route('/profile/edit', methods=['POST'])
    @login_required
    def edit_profile():
        bio = request.form.get('bio', '').strip()
        current_user.bio = bio

        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename != '' and allowed_file(file.filename):
                safe_name = secure_filename(file.filename)
                unique_name = generate_filename(safe_name)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
                current_user.avatar = unique_name

        db.session.commit()
        flash('Профиль успешно обновлен!', 'success')
        return redirect(url_for('profile', username=current_user.username))

    @app.route('/shopping-list')
    def shopping_list():
        return render_template('shopping_list.html')

    # Legacy routes compatibility
    @app.route('/my_recipes')
    @login_required
    def my_recipes():
        return redirect(url_for('profile', username=current_user.username))

    # ==================== ADMIN PANEL ====================
    @app.route('/admin')
    @login_required
    @admin_required
    def admin_dashboard():
        total_users = User.query.count()
        total_recipes = Recipe.query.count()
        total_reviews = Review.query.count()
        total_favorites = Favorite.query.count()

        recent_recipes = Recipe.query.order_by(Recipe.created_at.desc()).limit(5).all()
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()

        return render_template(
            'admin_dashboard.html',
            total_users=total_users,
            total_recipes=total_recipes,
            total_reviews=total_reviews,
            total_favorites=total_favorites,
            recent_recipes=recent_recipes,
            recent_users=recent_users
        )

    @app.route('/admin/recipes')
    @login_required
    @admin_required
    def admin_recipes():
        recipes = Recipe.query.order_by(Recipe.created_at.desc()).all()
        return render_template('admin_recipes.html', recipes=recipes)

    @app.route('/admin/users')
    @login_required
    @admin_required
    def admin_users():
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template('admin_users.html', users=users)

    @app.route('/admin/reviews')
    @login_required
    @admin_required
    def admin_reviews():
        reviews = Review.query.order_by(Review.created_at.desc()).all()
        return render_template('admin_reviews.html', reviews=reviews)

    @app.route('/admin/user/<int:user_id>/toggle-admin', methods=['POST'])
    @login_required
    @admin_required
    def admin_toggle_role(user_id):
        if user_id == current_user.id:
            flash('Вы не можете изменить роль собственного аккаунта!', 'error')
            return redirect(url_for('admin_users'))

        user = User.query.get_or_404(user_id)
        user.is_admin = not user.is_admin
        db.session.commit()
        status_str = 'Администратор' if user.is_admin else 'Пользователь'
        flash(f'Роль пользователя {user.username} изменена на: {status_str}', 'success')
        return redirect(url_for('admin_users'))

    @app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
    @login_required
    @admin_required
    def admin_delete_user(user_id):
        if user_id == current_user.id:
            flash('Вы не можете удалить свой собственный аккаунт!', 'error')
            return redirect(url_for('admin_users'))

        user = User.query.get_or_404(user_id)
        username = user.username

        # Cleanup image files of user recipes
        for recipe in user.recipes:
            for filename in recipe.get_images():
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass

        db.session.delete(user)
        db.session.commit()
        flash(f'Пользователь {username} и все его данные успешно удалены!', 'success')
        return redirect(url_for('admin_users'))

    # ==================== AUTHENTICATION ====================
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('index'))

        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')

            if not username or not email or not password:
                flash('Пожалуйста, заполните все обязательные поля!', 'error')
                return render_template('register.html')

            if len(password) < 6:
                flash('Пароль должен содержать не менее 6 символов!', 'error')
                return render_template('register.html')

            if password != confirm_password:
                flash('Введенные пароли не совпадают!', 'error')
                return render_template('register.html')

            if User.query.filter_by(username=username).first():
                flash('Пользователь с таким именем уже существует!', 'error')
                return render_template('register.html')

            if User.query.filter_by(email=email).first():
                flash('Пользователь с таким email уже зарегистрирован!', 'error')
                return render_template('register.html')

            user = User(username=username, email=email)
            user.set_password(password)

            # First user becomes admin automatically if no admin exists
            if User.query.count() == 0:
                user.is_admin = True

            db.session.add(user)
            db.session.commit()

            login_user(user)
            flash('Добро пожаловать в Recipe Collection! Регистрация прошла успешно.', 'success')
            return redirect(url_for('index'))

        return render_template('register.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))

        if request.method == 'POST':
            login_input = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            remember = bool(request.form.get('remember'))

            # Allow login via username or email
            user = User.query.filter(
                (User.username == login_input) | (User.email == login_input.lower())
            ).first()

            if user and user.check_password(password):
                login_user(user, remember=remember)
                flash(f'С возвращением, {user.username}!', 'success')
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('index'))
            else:
                flash('Неверное имя пользователя/email или пароль.', 'error')

        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('Вы успешно вышли из учетной записи.', 'info')
        return redirect(url_for('index'))

    # ==================== REST API ENDPOINTS ====================
    @app.route('/api/recipes', methods=['GET'])
    def api_recipes():
        page = request.args.get('page', 1, type=int)
        limit = min(request.args.get('limit', 10, type=int), 50)
        search = request.args.get('q', '').strip()
        cuisine = request.args.get('cuisine', '').strip()
        category = request.args.get('category', '').strip()

        query = Recipe.query
        if search:
            query = query.filter(Recipe.title.ilike(f"%{search}%"))
        if cuisine:
            query = query.filter(Recipe.cuisine == cuisine)
        if category and category != 'Все':
            query = query.filter(Recipe.category == category)

        pagination = query.order_by(Recipe.created_at.desc()).paginate(page=page, per_page=limit, error_out=False)

        return jsonify({
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': page,
            'recipes': [r.to_dict() for r in pagination.items]
        })

    @app.route('/api/recipes/<int:recipe_id>', methods=['GET'])
    def api_recipe_detail(recipe_id):
        recipe = Recipe.query.get_or_404(recipe_id)
        data = recipe.to_dict()
        data['parsed_ingredients'] = recipe.parsed_ingredients()
        data['parsed_instructions'] = recipe.parsed_instructions()
        data['reviews'] = [rev.to_dict() for rev in recipe.reviews]
        return jsonify(data)

    @app.route('/api/stats', methods=['GET'])
    def api_stats():
        return jsonify({
            'users_count': User.query.count(),
            'recipes_count': Recipe.query.count(),
            'reviews_count': Review.query.count(),
            'cuisines': app.config['CUISINES'],
            'categories': app.config['CATEGORIES']
        })

    # ==================== ERROR HANDLERS ====================
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500

    return app

app = create_app()

if __name__ == '__main__':
    from seed_data import seed_database
    with app.app_context():
        db.create_all()
        # Seed if empty
        if Recipe.query.count() == 0:
            seed_database()
    app.run(host='0.0.0.0', port=5000, debug=True)
