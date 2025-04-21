import os
import sys
import click
from flask.cli import with_appcontext
from app import create_app, db

app = create_app()

@click.group()
def cli():
    """Command line interface for managing the application."""
    pass

@cli.command()
@with_appcontext
def create_tables():
    """Create all database tables."""
    db.create_all()
    click.echo('Database tables created.')

@cli.command()
@with_appcontext
def drop_tables():
    """Drop all database tables."""
    if click.confirm('Are you sure you want to drop all tables? This will delete all data.'):
        db.drop_all()
        click.echo('Database tables dropped.')
    else:
        click.echo('Operation cancelled.')

@cli.command()
@with_appcontext
def reset_db():
    """Reset the database (drop and recreate all tables)."""
    if click.confirm('Are you sure you want to reset the database? This will delete all data.'):
        db.drop_all()
        db.create_all()
        click.echo('Database reset complete.')
    else:
        click.echo('Operation cancelled.')

@cli.command()
@click.argument('username')
@click.argument('email')
@click.argument('password')
@with_appcontext
def create_admin(username, email, password):
    """Create an admin user."""
    from models import User
    
    user = User.query.filter_by(username=username).first()
    if user:
        click.echo(f'User {username} already exists.')
        return
    
    admin = User(username=username, email=email, is_admin=True)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    click.echo(f'Admin user {username} created successfully.')

if __name__ == '__main__':
    cli()
