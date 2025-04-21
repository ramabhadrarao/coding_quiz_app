from app import create_app
from models import db, User
from datetime import datetime

app = create_app()

@app.cli.command("init-db")
def init_db():
    """Initialize the database with schema and initial data."""
    db.drop_all()
    db.create_all()
    
    # Create admin user if not exists
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', email='admin@example.com', is_admin=True)
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()
            print('Admin user created: admin/admin')

if __name__ == '__main__':
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
        
        # Create admin user if not exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', email='admin@example.com', is_admin=True)
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()
            print('Admin user created: admin/admin')
    
    app.run(debug=True)
