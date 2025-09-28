# Requirements
+ Python 3.11

# Web Documentation
To see the frontend function
```
http://127.0.0.1:8000/docs
```

# 1 Setup locally for new machine, only do once (windows 10/11) 
1. Clone GitHub Repo to local
2. Open CMD, then in CMD:
3. change directory to local repo: cd 'directory_of_repo', insert your login username in 'username'
```
cd C:\Users\(username)\Documents\Project\Smart_Kamera_Web
```

4. Create python env: 
```
python -m venv .venv
```
5. Start environemtn: 
```
.\.venv\Scripts\activate 
```
Should see (.venv) in console
6. Install dependencies: 
```
python -m pip install --upgrade pip setuptools wheel

pip install -r requirements.txt
   ```
7. In case of errors regarding -e when installing requirements.txt:
```
pip install -e .\libs\ocr_core

pip install -r .\requirements.txt --no-deps 
```
8. Run sanity check for any missing modules:
```
python sanity_check.py
```
Result should be "All required modules are importable"
If list of missing modules shown, then install each one with 
```
pip install (Module name)
```
9. Run App locally:
```
python backend\run_local.py
```
Open any browser, then paste local address: 
```
http://127.0.0.1:8000/ui 
```

# 2 If setup is done and simply start the web app locally
1. Start environemtn:
```
.\.venv\Scripts\activate 
```
2. run web app: 
```
python backend\run_local.py
```
# 3 (Experimental) Run all above with a single click
1. Hold Ctrl and right click setup_env.ps1 in root folder, then "Run with PowerShell"

# Troubleshotting (Errors)
## Error:
ModuleNotFoundError: No module named 'fastapi'

ModuleNotFoundError: No module named 'ocr_core'
## Fix:
Activate the venv: 
```
.\.venv\Scripts\activate
```

Verify Python path: 
```
where python
```
```
python -c "import sys; print(sys.executable)"
```

Should get '...\Smart_Kamera_Web\.venv\Scripts\python.exe'

## Error:
ImportError: Could not import OCRProcessor. Tried: ocr_core.vendors.class_easyOCR_V1, ...

## Fix:
Make sure these files exists: 

libs\ocr_core\ocr_core\vendors\class_easyOCR_V1.py

libs\ocr_core\ocr_core\vendors\__init__.py

Then reinstall: 
```
pip install -e .\libs\ocr_core
```

## Error (mismtach libraries):
RuntimeError: Numpy is not available

OSError: [WinError 1920] The file cannot be accessed by the system. Error loading shm.dll

## Fix (run each line at a time): 
```
pip uninstall -y numpy opencv-python opencv-python-headless

pip install numpy==1.26.4 opencv-python-headless==4.8.1.78

pip install --no-cache-dir torch==2.3.1 torchvision==0.18.1 --index-url https://download.pytorch.org/whl/cpu

pip install "scipy>=1.11,<1.12" "scikit-image>=0.21,<0.25"
```
## Error (missing deps):
ModuleNotFoundError: No module named 'click'

ModuleNotFoundError: No module named 'h11'

## Fix:
```
pip install click h11
```

## Error (ModuleNotFoundError: backend)

## Fix:
Ensure backend/__init__.py exists (empty file is fine).
```
python backend\run_local.py 
```
## Error:
ModuleNotFoundError: No module named 'pyclipper'

ModuleNotFoundError: No module named 'python-bidi'

## Fix:
```
pip install ninja opencv-python-headless pyclipper python-bidi PyYAML scikit-image scipy Shapely
```

## Error:
ModuleNotFoundError: No module named 'contourpy'

ModuleNotFoundError: No module named 'kiwisolver'

## Fix:
```
pip install contourpy cycler fonttools kiwisolver pyparsing
```



# Deployed on render.com
## Link to site
https://mkv-aql.github.io/Smart_Kamera_Web/

## Link to deployment

# Deployed on Azure 

