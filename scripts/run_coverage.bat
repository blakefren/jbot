@echo off
python -m coverage run --branch --source=src,data,db -m unittest discover -s . -p "test_*.py"
if errorlevel 1 exit /b %errorlevel%
python -m coverage report --show-missing --fail-under=80