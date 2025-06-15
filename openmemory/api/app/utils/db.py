from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models import User, App
from typing import Tuple
import logging

logger = logging.getLogger(__name__)


def get_or_create_user(db: Session, user_id: str) -> User:
    """Get or create a user with the given user_id"""
    # 先尝试获取
    user = db.query(User).filter(User.user_id == user_id).first()
    if user:
        return user
    
    try:
        # 尝试创建新用户
        user = User(user_id=user_id)
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created new user: {user_id}")
        return user
    except IntegrityError:
        # 如果出现唯一性约束冲突，回滚并重新查询
        db.rollback()
        logger.warning(f"User {user_id} already exists (race condition), fetching existing user")
        user = db.query(User).filter(User.user_id == user_id).first()
        if user:
            return user
        else:
            raise Exception(f"Failed to get or create user: {user_id}")


def get_or_create_app(db: Session, user: User, app_id: str) -> App:
    """Get or create an app for the given user"""
    # 先尝试获取
    app = db.query(App).filter(App.owner_id == user.id, App.name == app_id).first()
    if app:
        return app
    
    try:
        # 尝试创建新应用
        app = App(owner_id=user.id, name=app_id)
        db.add(app)
        db.commit()
        db.refresh(app)
        logger.info(f"Created new app: {app_id} for user: {user.user_id}")
        return app
    except IntegrityError:
        # 如果出现唯一性约束冲突，回滚并重新查询
        db.rollback()
        logger.warning(f"App {app_id} for user {user.user_id} already exists (race condition), fetching existing app")
        app = db.query(App).filter(App.owner_id == user.id, App.name == app_id).first()
        if app:
            return app
        else:
            raise Exception(f"Failed to get or create app: {app_id} for user: {user.user_id}")


def get_user_and_app(db: Session, user_id: str, app_id: str) -> Tuple[User, App]:
    """Get or create both user and their app"""
    user = get_or_create_user(db, user_id)
    app = get_or_create_app(db, user, app_id)
    return user, app
