import os
import sys
import time
import urllib.parse
import hashlib  
from datetime import datetime
import requests
import exifread
from PIL import Image
from colorama import init, Fore, Style


TK_AVAILABLE = True
try:
    from tkinter import Tk, filedialog
except Exception:
    TK_AVAILABLE = False


init(autoreset=True)
IMGBB_API_KEY = "" #API KEY from https://api.imgbb.com/

BANNER = r"""
 .----..-. .-.  .--.  .-.-.     .-. .-..-. .-..-. .-..-----. 
{ {__-`|  \{ | / {} \ | } }}    { {_} || } { ||  \{ |`-' '-' 
.-._} }| }\  {/  /\  \| |-'     | { } }\ `-' /| }\  {  } {   
`----' `-' `-'`-'  `-'`-'       `-' `-' `---' `-' `-'  `-'   
              github.com/RichardAlmeyda
"""

HEADERS = {
    "User-Agent": "SnapHunt/1.0 (OSINT educational tool)"
}


def hr(title: str):
    print(Fore.CYAN + f"\n==== {title} ====")

def good(msg: str):
    print(Fore.GREEN + "[+] " + msg)

def info(msg: str):
    print(Fore.YELLOW + "[*] " + msg)

def warn(msg: str):
    print(Fore.RED + "[!] " + msg)

def file_hashes(path: str) -> list[str]:
    """Generate MD5, SHA1, SHA256 of a file."""
    hashes = {"MD5": hashlib.md5(), "SHA1": hashlib.sha1(), "SHA256": hashlib.sha256()}
    try:
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                for h in hashes.values():
                    h.update(chunk)
        return [f"{name}: {h.hexdigest()}" for name, h in hashes.items()]
    except Exception as e:
        return [f"Hashing failed: {e}"]

def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

def choose_image_path() -> str:
    """
    Menu: 1) GUI file chooser (if available)  2) Manual path input  0) Quit
    """
    print(Fore.MAGENTA + BANNER)
    print(Fore.CYAN + "Welcome to SnapHunt! Let's find the origins and info about your image.\n")
    print(Fore.YELLOW + "Select input method:")
    print("  1) GUI file picker" + ("" if TK_AVAILABLE else Fore.RED + "  (tkinter not available)"))
    print(Fore.YELLOW + "  2) Type a file path manually")
    print(Fore.YELLOW + "  0) Quit")

    while True:
        choice = input(Fore.CYAN + "\nYour choice [1/2/0]: ").strip()
        if choice == "0":
            warn("User chose to quit. Bye!")
            sys.exit(0)

        if choice == "1":
            if not TK_AVAILABLE:
                warn("tkinter is not available. Please choose option 2 for manual path.")
                continue
            try:
                root = Tk()
                root.withdraw()
                file_path = filedialog.askopenfilename(
                    title="Select an image file",
                    filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tiff;*.webp")]
                )
                root.destroy()
            except Exception as e:
                warn(f"GUI open failed: {e}")
                file_path = ""

            if file_path and os.path.isfile(file_path):
                good(f"Selected file: {file_path}")
                return file_path
            else:
                warn("No file selected or invalid. Try again.")
                continue

        if choice == "2":
            file_path = input(Fore.CYAN + "Enter the full path to your image: ").strip('"').strip()
            if os.path.isfile(file_path):
                good(f"Selected file: {file_path}")
                return file_path
            else:
                warn("File not found. Please try again.")


def upload_imgbb(image_path: str) -> str | None:

    try:
        with open(image_path, "rb") as f:
            info("Uploading image to imgbb...")
            r = requests.post(
                "https://api.imgbb.com/1/upload",
                params={"key": IMGBB_API_KEY},
                files={"image": f},
                timeout=60
            )
        data = r.json()
        if data.get("success"):
            url = data["data"]["url"]
            good("Upload successful.")
            return url
        else:
            warn(f"Upload failed: {data.get('error')}")
            return None
    except requests.exceptions.RequestException as e:
        warn(f"Network error during upload: {e}")
        return None
    except Exception as e:
        warn(f"Unexpected error during upload: {e}")
        return None

def exif_gps(path: str):
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f)
        lat = tags.get("GPS GPSLatitude")
        lon = tags.get("GPS GPSLongitude")
        lat_ref = tags.get("GPS GPSLatitudeRef")
        lon_ref = tags.get("GPS GPSLongitudeRef")
        if not (lat and lon and lat_ref and lon_ref):
            return None

        def _to_deg(values):
            d, m, s = values.values
            return (float(d.num) / d.den) + (float(m.num) / m.den) / 60 + (float(s.num) / s.den) / 3600

        lat_val = _to_deg(lat)
        lon_val = _to_deg(lon)
        if str(lat_ref.values).strip() != "N":
            lat_val = -lat_val
        if str(lon_ref.values).strip() != "E":
            lon_val = -lon_val
        return (lat_val, lon_val)
    except Exception:
        return None

def reverse_geocode(lat: float, lon: float) -> dict | None:
    """
    Free reverse geocoding via OpenStreetMap Nominatim.
    Be nice: include a UA and a short sleep for courtesy.
    """
    try:
        time.sleep(1)  
        params = {
            "format": "jsonv2",
            "lat": f"{lat}",
            "lon": f"{lon}",
            "zoom": "18",
            "addressdetails": "1"
        }
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            headers=HEADERS,
            params=params,
            timeout=30
        )
        if r.status_code == 200:
            return r.json()
        else:
            warn(f"Nominatim responded with status {r.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        warn(f"Reverse geocoding failed: {e}")
        return None

def image_info(path: str):
    try:
        img = Image.open(path)
        return [
            f"Format: {img.format}",
            f"Size: {img.size[0]}x{img.size[1]}",
            f"Mode: {img.mode}"
        ]
    except Exception:
        return ["Unable to read image metadata"]

def generate_reverse_links(public_url: str) -> dict:
    encoded = urllib.parse.quote(public_url, safe="")
    return {
        "Google Lens": f"https://lens.google.com/uploadbyurl?url={encoded}",
        "Yandex": f"https://yandex.com/images/search?rpt=imageview&url={encoded}",
        "Bing Images": f"https://www.bing.com/images/search?view=detailv2&iss=SBI&form=SBIIRP&sbisrc=UrlPaste&q=imgurl:{encoded}",
        "TinEye": f"https://tineye.com/search?url={encoded}",
        "SauceNAO": f"https://saucenao.com/search.php?url={encoded}",
    }

def print_section(title: str, rows: list[str]):
    hr(title)
    for line in rows:
        print(Fore.YELLOW + line)

# ---------- Main ----------
def main():
    file_path = choose_image_path()
    report_lines = [f"SnapHunt Image OSINT Report", f"Timestamp: {datetime.now()}", f"Local file: {file_path}", ""]

    meta = image_info(file_path)
    print_section("IMAGE METADATA", meta)
    report_lines.extend(["[IMAGE METADATA]"] + meta + [""])


    hashes = file_hashes(file_path)
    print_section("FILE HASHES", hashes)
    report_lines.extend(["[FILE HASHES]"] + hashes + [""])


    public_url = upload_imgbb(file_path)
    if public_url:
        print_section("PUBLIC IMAGE URL", [public_url])
        report_lines.extend(["[PUBLIC IMAGE URL]", public_url, ""])
    else:
        warn("Public URL unavailable; reverse-image links will be limited.")
        report_lines.append("[!] Public URL not available")
        report_lines.append("")


    gps = exif_gps(file_path)
    if gps:
        lat, lon = gps
        maps_link = f"https://maps.google.com/?q={lat},{lon}"
        gps_rows = [
            f"Latitude: {lat}",
            f"Longitude: {lon}",
            f"Google Maps: {maps_link}"
        ]
        print_section("GPS DATA", gps_rows)
        report_lines.extend(["[GPS DATA]"] + gps_rows)

        geo = reverse_geocode(lat, lon)
        if geo:
            addr = geo.get("address", {})
            display = geo.get("display_name", "")
            country = addr.get("country", "Unknown")
            state = addr.get("state") or addr.get("region") or ""
            city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("hamlet") or ""
            road = addr.get("road") or ""
            house = addr.get("house_number") or ""
            approx_rows = [
                f"Display: {display}",
                f"Country: {country}",
                f"State/Region: {state}",
                f"City/Locality: {city}",
                f"Road: {road}",
                f"House No: {house}"
            ]
            print_section("POSSIBLE ADDRESS (Reverse Geocoded)", approx_rows)
            report_lines.extend(["[REVERSE GEOCODE]"] + approx_rows + [""])
        else:
            warn("Could not reverse-geocode GPS coordinates.")
            report_lines.append("[!] Reverse geocoding failed\n")
    else:
        warn("No GPS metadata found in image EXIF.")
        report_lines.append("[!] No GPS metadata found\n")


    if public_url:
        links = generate_reverse_links(public_url)
        link_rows = [f"{name}: {url}" for name, url in links.items()]
        print_section("REVERSE IMAGE SEARCH LINKS", link_rows)
        report_lines.extend(["[REVERSE IMAGE SEARCH LINKS]"] + link_rows + [""])
    else:
        warn("Skipping reverse search links because no public URL was created.")

    # 6) Save report
    out_name = f"SnapHunt_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(out_name, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    good(f"Full report saved to {out_name}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        warn("Interrupted by user. Exiting.")
