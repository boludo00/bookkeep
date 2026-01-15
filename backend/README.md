# Book Hound Backend

FastAPI backend for the Book Hound application.

## Setup

### Using Docker Compose (Recommended)

The backend is configured to run via Docker Compose. See the main project README for instructions.

### Local Development

1. Install uv (if not already installed):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Install dependencies using uv:
```bash
uv pip install -r requirements.txt
```

Alternatively, you can use pip:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
export DATABASE_URL=postgresql://bookhound:bookhound_password@localhost:5432/bookhound_db
```

4. Run the server:
```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

## API Documentation

Once the server is running, you can access:
- Interactive API docs: `http://localhost:8000/docs`
- Alternative docs: `http://localhost:8000/redoc`

## Endpoints

### Users
- `POST /api/users/` - Create a new user
- `GET /api/users/` - List all users
- `GET /api/users/{user_id}` - Get user by ID

### Books
- `POST /api/books/` - Create a new book
- `GET /api/books/` - List all books
- `GET /api/books/{book_id}` - Get book by ID
- `PUT /api/books/{book_id}` - Update a book
- `DELETE /api/books/{book_id}` - Delete a book

## Database

The backend uses PostgreSQL with SQLAlchemy ORM. Database models are defined in `app/models.py`.

