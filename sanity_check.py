modules = [
    # Web / backend
    "fastapi","uvicorn","click","h11","python_multipart","watchfiles",
    # Image / data utils
    "PIL","cv2","numpy","pandas",
    # OCR stack
    "torch","torchvision","easyocr","ninja","pyclipper","bidi.algorithm","yaml","skimage","scipy","shapely",
    # Plotting
    "matplotlib","contourpy","cycler","fontTools","kiwisolver","pyparsing",
    # Your local package
    "ocr_core","ocr_core.vendors.class_easyOCR_V1",
]
failed=[]
for m in modules:
    try: __import__(m)
    except Exception as e: failed.append((m,str(e)))
print("="*40)
print("All required modules are importable." if not failed else "Missing/broken modules:")
for name, err in failed: print(f"  {name}: {err}")
print("="*40)
