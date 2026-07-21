#!/usr/bin/env python
"""
Room 120 - Complete startup and initialization script
Run this to set up and start the application
"""

import os
import sys
import subprocess
from pathlib import Path

def print_header(text):
    """Print a formatted header"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60 + "\n")

def check_env():
    """Check if .env file exists"""
    if not Path('.env').exists():
        print_header("⚠️  ERROR: .env file not found")
        print("Create .env file with your Toast credentials:")
        print("\n1. Copy .env.example to .env")
        print("2. Fill in your Toast API credentials")
        print("3. Run this script again\n")
        sys.exit(1)
    print_header("✓ .env file found")

def check_dependencies():
    """Check if all required packages are installed"""
    print_header("Checking dependencies")
    
    required = [
        'flask',
        'flask-sqlalchemy',
        'python-dotenv',
        'requests',
    ]
    
    try:
        import pkg_resources
        installed = {pkg.key for pkg in pkg_resources.working_set}
        
        missing = [pkg for pkg in required if pkg.lower() not in installed]
        
        if missing:
            print(f"Missing packages: {', '.join(missing)}")
            print("\nInstalling missing packages...")
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install'] + missing
            )
            print("✓ Packages installed\n")
        else:
            print("✓ All dependencies installed\n")
    except Exception as e:
        print(f"Warning: Could not check dependencies: {e}\n")

def create_directories():
    """Create required directories"""
    print_header("Setting up directories")
    
    dirs = ['logs', 'uploads', 'instance']
    
    for dir_name in dirs:
        Path(dir_name).mkdir(exist_ok=True)
        print(f"✓ {dir_name}/")
    print()

def init_database():
    """Initialize the database"""
    print_header("Initializing database")
    
    try:
        from app import app, db
        
        with app.app_context():
            db.create_all()
            print("✓ Database initialized\n")
    except Exception as e:
        print(f"Warning: Could not initialize database: {e}\n")

def test_imports():
    """Test that all imports work"""
    print_header("Testing imports")
    
    try:
        from app import app
        print("✓ app.py imports successfully")
        
        from models import User
        print("✓ models.py imports successfully")
        
        from toast_api import get_draft_room_orders
        print("✓ toast_api.py imports successfully")
        
        from member_import import parse_csv_file
        print("✓ member_import.py imports successfully")
        
        print()
    except Exception as e:
        print(f"✗ Import error: {e}\n")
        sys.exit(1)

def print_startup_info():
    """Print startup information"""
    print_header("Room 120 Ready to Start")
    
    print("To start the application, run:\n")
    print("  python app.py")
    print("\nOr use Flask directly:\n")
    print("  flask run")
    print("\nThen open your browser to:")
    print("  http://localhost:5000")
    print("\nKey URLs:")
    print("  Login:              http://localhost:5000/login")
    print("  Register:           http://localhost:5000/register")
    print("  Admin Panel:        http://localhost:5000/admin/dashboard")
    print("  Sales Report:       http://localhost:5000/admin/sales-report")
    print("  Import Members:     http://localhost:5000/import_members")
    print("\nPress Ctrl+C to stop the server\n")

def main():
    """Main startup sequence"""
    print("\n")
    print("╔════════════════════════════════════════════════════════╗")
    print("║           Room 120 - Startup & Initialization          ║")
    print("╚════════════════════════════════════════════════════════╝")
    
    check_env()
    check_dependencies()
    create_directories()
    init_database()
    test_imports()
    print_startup_info()

if __name__ == '__main__':
    main()