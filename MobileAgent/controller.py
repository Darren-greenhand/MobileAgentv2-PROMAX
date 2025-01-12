import os
import time
import subprocess
from PIL import Image


def get_screenshot(adb_path,log_dir,iter):
    command = adb_path + " shell rm /sdcard/screenshot.png"
    subprocess.run(command, capture_output=True, text=True, shell=True)
    time.sleep(1)
    command = adb_path + " shell screencap -p /sdcard/screenshot.png"
    subprocess.run(command, capture_output=True, text=True, shell=True)
    time.sleep(1)
    command = adb_path + " pull /sdcard/screenshot.png ./screenshot"
    subprocess.run(command, capture_output=True, text=True, shell=True)
    time.sleep(1)

    command = adb_path + " shell uiautomator dump /sdcard/ui_dump.xml"
    subprocess.run(command, capture_output=True, text=True, shell=True)
    time.sleep(1)
    command = adb_path + " pull /sdcard/ui_dump.xml /shd/jcy/project/Mobile-Agent-v2"
    subprocess.run(command, capture_output=True, text=True, shell=True)
    time.sleep(1)

    image_path = "./screenshot/screenshot.png"
    save_path = "./screenshot/screenshot.jpg"
    image = Image.open(image_path)
    image.convert("RGB").save(save_path, "JPEG")
    #复制一份到log_dir
    os.system(f'cp {save_path} "{log_dir}"/{iter}.jpg')
    os.remove(image_path)
    # if os.path.exists(image_path):
    #      image = Image.open(image_path)
    #      image.convert("RGB").save(save_path, "JPEG")

    #      # Copy to log directory
    #      os.system(f'cp {save_path} "{log_dir}"/{iter}.jpg')
    #      os.remove(image_path)
    # else:
    #      print(f"Screenshot not found at {image_path}")

def clear(adb_path):
    command = adb_path + " shell input keyevent KEYCODE_MOVE_END"
    subprocess.run(command, capture_output=True, text=True, shell=True)
    for i in range(30):
        command = adb_path + " shell input keyevent KEYCODE_DEL"
        subprocess.run(command, capture_output=True, text=True, shell=True)

def tap(adb_path, x, y):
    command = adb_path + f" shell input tap {x} {y}"
    subprocess.run(command, capture_output=True, text=True, shell=True)


def type(adb_path, text):
    text = text.replace("\\n", "_").replace("\n", "_")
    for char in text:
        if char == ' ':
            command = adb_path + f" shell input text %s"
            subprocess.run(command, capture_output=True, text=True, shell=True)
        elif char == '_':
            command = adb_path + f" shell input keyevent 66"
            subprocess.run(command, capture_output=True, text=True, shell=True)
        elif 'a' <= char <= 'z' or 'A' <= char <= 'Z' or char.isdigit():
            command = adb_path + f" shell input text {char}"
            subprocess.run(command, capture_output=True, text=True, shell=True)
        elif char in '-.,!?@\'°/:;()':
            command = adb_path + f" shell input text \"{char}\""
            subprocess.run(command, capture_output=True, text=True, shell=True)
        else:
            command = adb_path + f" shell am broadcast -a ADB_INPUT_TEXT --es msg \"{char}\""
            subprocess.run(command, capture_output=True, text=True, shell=True)


def slide(adb_path, x1, y1, x2, y2):
    command = adb_path + f" shell input swipe {x1} {y1} {x2} {y2} 500"
    subprocess.run(command, capture_output=True, text=True, shell=True)


def back(adb_path):
    command = adb_path + f" shell input keyevent 4"
    subprocess.run(command, capture_output=True, text=True, shell=True)
    
    
def home(adb_path):
    command = adb_path + f" shell am start -a android.intent.action.MAIN -c android.intent.category.HOME"
    subprocess.run(command, capture_output=True, text=True, shell=True)
