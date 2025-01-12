import subprocess
import time

def take_screenshot(device_name, output_file):
    # Capture the screenshot on the device
    subprocess.run(["adb", "-s", device_name, "shell", "screencap", "-p", "/sdcard/screen.png"])
    # Pull the screenshot from the device to the local machine
    subprocess.run(["adb", "-s", device_name, "pull", "/sdcard/screen.png", output_file])

def main():
    device_name = "emulator-5556"  # Default device name for the first emulator instance
    while True:
        take_screenshot(device_name, "/shd/jcy/project/Mobile-Agent-v2/watching/screenshot.png")
        print("Screenshot taken and saved as screenshot.png")
        time.sleep(1)  # Wait for 5 seconds before taking the next screenshot

if __name__ == "__main__":
    main()
