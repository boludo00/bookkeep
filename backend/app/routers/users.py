from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
import bcrypt
from app import database, models, schemas
from app.auth import get_current_user, get_current_user_optional, require_admin

router = APIRouter()


def get_password_hash(password: str) -> str:
    # Ensure password is a string and bytes
    if not isinstance(password, str):
        password = str(password)
    # Truncate to 72 bytes if necessary (bcrypt limitation)
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        # Truncate byte-by-byte to avoid breaking UTF-8 sequences
        truncated_bytes = password_bytes[:72]
        # Try to decode, if it fails (incomplete UTF-8 sequence), remove last byte
        try:
            password = truncated_bytes.decode('utf-8')
        except UnicodeDecodeError:
            password = truncated_bytes[:-1].decode('utf-8', errors='ignore')
        password_bytes = password.encode('utf-8')
    # Use bcrypt directly to avoid passlib initialization issues
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Ensure password is bytes
    if not isinstance(plain_password, str):
        plain_password = str(plain_password)
    password_bytes = plain_password.encode('utf-8')
    if len(password_bytes) > 72:
        # Truncate same way as in hash
        truncated_bytes = password_bytes[:72]
        try:
            plain_password = truncated_bytes.decode('utf-8')
        except UnicodeDecodeError:
            plain_password = truncated_bytes[:-1].decode('utf-8', errors='ignore')
        password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


@router.get("/me", response_model=schemas.UserResponse)
async def get_current_user_info(
    current_user: models.User = Depends(get_current_user)
):
    """Get the current logged-in user's information"""
    return current_user


class PasswordChangeRequest(schemas.BaseModel):
    current_password: str
    new_password: str


@router.put("/me/password")
async def change_password(
    request: PasswordChangeRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Change the current user's password"""
    # Verify current password
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Update password
    current_user.hashed_password = get_password_hash(request.new_password)
    db.commit()

    return {"message": "Password changed successfully"}


@router.get("/check/admin-exists", response_model=dict)
def check_admin_exists(db: Session = Depends(database.get_db)):
    """Check if any admin users exist (public endpoint for initial setup)"""
    admin_count = db.query(models.User).filter(models.User.is_admin == True).count()
    return {"admin_exists": admin_count > 0}


@router.get("/{user_id}", response_model=schemas.UserResponse)
async def get_user(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return db_user


@router.get("/", response_model=list[schemas.UserResponse])
async def get_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    users = db.query(models.User).offset(skip).limit(limit).all()
    return users


@router.post("/", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user: schemas.UserCreate,
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional)
):
    """
    Create a new user.
    - If no admin exists, this endpoint is public and creates the first admin.
    - If admins exist, only admins can create new users.
    """
    # Check if admin users exist
    admin_exists = db.query(models.User).filter(models.User.is_admin == True).first() is not None

    if admin_exists:
        if not current_user or not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can create new users"
            )

    # Validate password length (bcrypt has a 72-byte limit)
    password_bytes = user.password.encode('utf-8')
    if len(password_bytes) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password cannot be longer than 72 bytes. Please use a shorter password."
        )

    if len(user.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long"
        )

    # Check if user already exists
    db_user = db.query(models.User).filter(
        (models.User.email == user.email) | (models.User.username == user.username)
    ).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username already registered"
        )

    # Create new user
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        hashed_password=hashed_password,
        is_admin=user.is_admin if not admin_exists else False,  # First user is always admin
        can_request_ebook=user.can_request_ebook if user.can_request_ebook is not None else True,
        can_request_audiobook=user.can_request_audiobook if user.can_request_audiobook is not None else True,
        auto_approve_ebooks=user.auto_approve_ebooks if user.auto_approve_ebooks is not None else True,
        auto_approve_audiobooks=user.auto_approve_audiobooks if user.auto_approve_audiobooks is not None else True,
    )

    # If no admin exists, make this user an admin (regardless of is_admin flag)
    if not admin_exists:
        db_user.is_admin = True

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.put("/{user_id}", response_model=schemas.UserResponse)
async def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """Update user information and permissions (admin only)"""
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Update fields if provided
    if user_update.email is not None:
        # Check if email is already taken by another user
        existing = db.query(models.User).filter(
            models.User.email == user_update.email,
            models.User.id != user_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        db_user.email = user_update.email

    if user_update.username is not None:
        # Check if username is already taken by another user
        existing = db.query(models.User).filter(
            models.User.username == user_update.username,
            models.User.id != user_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
        db_user.username = user_update.username

    if user_update.full_name is not None:
        db_user.full_name = user_update.full_name

    if user_update.is_active is not None:
        db_user.is_active = user_update.is_active

    if user_update.is_admin is not None:
        db_user.is_admin = user_update.is_admin

    if user_update.auto_approve_ebooks is not None:
        db_user.auto_approve_ebooks = user_update.auto_approve_ebooks

    if user_update.auto_approve_audiobooks is not None:
        db_user.auto_approve_audiobooks = user_update.auto_approve_audiobooks

    if user_update.can_request_ebook is not None:
        db_user.can_request_ebook = user_update.can_request_ebook

    if user_update.can_request_audiobook is not None:
        db_user.can_request_audiobook = user_update.can_request_audiobook

    if user_update.can_download is not None:
        db_user.can_download = user_update.can_download

    # Prevent removing the last admin
    if user_update.is_admin is False and db_user.is_admin:
        admin_count = db.query(models.User).filter(
            models.User.is_admin == True,
            models.User.id != user_id
        ).count()
        if admin_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove admin privileges from the last admin"
            )

    db.commit()
    db.refresh(db_user)
    return db_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_admin)
):
    """Delete a user (admin only)"""
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Prevent deleting the last admin
    if db_user.is_admin:
        admin_count = db.query(models.User).filter(
            models.User.is_admin == True,
            models.User.id != user_id
        ).count()
        if admin_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the last admin user"
            )

    db.delete(db_user)
    db.commit()
    return None
