from typing import Any
import requests
from requests_ntlm2 import HttpNtlmAuth
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString
import time
import json
import os
import dotenv
import re
from openai import OpenAI
import copy

# Patch for MD4 support in Python 3.13
import hashlib

try:
    hashlib.new("md4")
except ValueError:
    # MD4 not available, try to use pycryptodome
    try:
        from Crypto.Hash import MD4

        class MD4Wrapper:
            def __init__(self, data=b""):
                self._hash = MD4.new()
                if data:
                    self._hash.update(data)

            def update(self, data):
                self._hash.update(data)

            def digest(self):
                return self._hash.digest()

            def hexdigest(self):
                return self._hash.hexdigest()

        original_new = hashlib.new

        def patched_new(name, data=b""):
            if name == "md4":
                return MD4Wrapper(data)
            return original_new(name, data)

        hashlib.new = patched_new
    except ImportError:
        pass

dotenv.load_dotenv()

USERNAME = os.getenv("GUC_USERNAME")
PASSWORD = os.getenv("GUC_PASSWORD")
NOTIFICATION_ENDPOINT = os.getenv("NOTIFICATION_ENDPOINT")
NOTIFICATIONS_API_KEY = os.getenv("NOTIFICATIONS_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SEND_NOTIFICATIONS = os.getenv("SEND_NOTIFICATIONS", "true").lower() in (
    "true",
    "1",
    "yes",
)
USE_OPENAI = os.getenv("USE_OPENAI", "false").lower() in ("true", "1", "yes")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "10"))  # Default to 10 retries
RETRY_BASE_DELAY = int(os.getenv("RETRY_BASE_DELAY", "10"))  # 10 seconds
RETRY_MAX_DELAY = int(os.getenv("RETRY_MAX_DELAY", "300"))  # 5 minutes
POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "3600"))  # 1 hour

if not USERNAME or not PASSWORD:
    exit("Environment variables GUC_USERNAME and GUC_PASSWORD must be set")

if not NOTIFICATION_ENDPOINT:
    exit("Environment variable NOTIFICATION_ENDPOINT must be set")

if not NOTIFICATIONS_API_KEY:
    exit("Environment variable NOTIFICATIONS_API_KEY must be set")

if not OPENAI_API_KEY:
    exit("Environment variable OPENAI_API_KEY must be set")

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

auth = HttpNtlmAuth(USERNAME, PASSWORD)


def fetch_all_courses() -> list[tuple[str, str, int, int]]:
    """Fetch all courses for the current user from the latest season."""
    res = requests.get(
        "https://cms.guc.edu.eg/apps/student/ViewAllCourseStn", auth=auth
    )
    if res.status_code == 401:
        exit("❌ Authentication failed")

    soup = BeautifulSoup(res.content, "html.parser")

    # Get all course names, IDs, and season IDs using single selectors
    table = soup.select_one("table")
    if not table:
        exit("❌ No courses found")
    course_name_cells = table.select("td:nth-child(2)")
    course_id_cells = table.select("td:nth-child(4)")
    season_id_cells = table.select("td:nth-child(5)")

    courses = []
    # Ensure all arrays have the same length
    min_length = min(len(course_name_cells), len(course_id_cells), len(season_id_cells))

    for i in range(min_length):
        course_name_text = course_name_cells[i].get_text(strip=True)

        # Extract course code from the pattern (|CODE|) and full course name
        course_code_match = re.search(r"\(\|(.+?)\|\)", course_name_text)
        if course_code_match:
            course_code = course_code_match.group(1)
            # Extract the full course name after the code pattern
            course_name = re.sub(r"\(\|.+?\|\)\s*", "", course_name_text).strip()
            # Remove the course ID number at the end (e.g., " (45)")
            course_name = re.sub(r"\s*\(\d+\)$", "", course_name).strip()
        else:
            course_code = course_name_text.strip()
            course_name = course_name_text.strip()

        try:
            course_id = int(course_id_cells[i].get_text(strip=True))
            season_id = int(season_id_cells[i].get_text(strip=True))
            courses.append((course_code, course_name, course_id, season_id))
        except ValueError:
            # Skip rows where course_id or season_id can't be parsed as integers
            continue

    return courses


def fetch_page(url: str) -> BeautifulSoup:
    """Fetch a specific page."""
    res = requests.get(url, auth=auth, headers={"User-Agent": "Mozilla/5.0"})
    if res.status_code == 401:
        exit("❌ Authentication failed")
    return BeautifulSoup(res.text, "html.parser")


def parse_description(html: BeautifulSoup) -> str | None:
    element = html.select_one("#ContentPlaceHolderright_ContentPlaceHoldercontent_desc")

    if element is None:
        return None

    # Clone the element to avoid modifying the original
    element_copy = copy.copy(element)

    # Replace tables with placeholder to avoid spread-out content
    for table in element_copy.find_all("table"):
        table.replace_with(NavigableString("\n[TABLE]\n"))

    # Replace br tags with newlines
    for br in element_copy.find_all("br"):
        br.replace_with(NavigableString("\n"))

    # Replace block elements with newlines
    for tag in element_copy.find_all(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6"]):
        tag.replace_with(NavigableString("\n" + tag.get_text() + "\n"))

    # Replace list items with newlines and bullets
    for li in element_copy.find_all("li"):
        li.replace_with(NavigableString("\n• " + li.get_text()))

    # Get the text and clean up
    description = element_copy.get_text()

    # Normalize whitespace: remove extra spaces but keep single newlines
    lines = []
    for line in description.split("\n"):
        cleaned_line = " ".join(line.split())  # Remove extra spaces
        lines.append(cleaned_line)

    # Remove empty lines and join
    description = "\n".join(line for line in lines if line.strip())

    return description


def parse_files(html: BeautifulSoup) -> list[dict[str, str]]:
    soup = html.select(".weeksdata .card-body > div:nth-child(1)")

    elements: list[dict[str, Tag | None]] = [
        {
            "filename": element.select_one("strong"),
            "category": element,
        }
        for element in soup
    ]

    files: list[dict[str, str]] = [
        {
            "filename": file["filename"].get_text(strip=True),
            "category": file["category"].get_text(strip=True),
        }
        for file in elements
        if file["filename"] is not None and file["category"] is not None
    ]

    files = [
        {
            "filename": re.sub(r"^\d+\s*\-\s*", "", file["filename"]),
            "category": re.findall(r"\((.+?)\)", file["category"])[-1].strip(),
        }
        for file in files
    ]
    return files


def save_version(content, filename: str) -> None:
    with open(filename, "w") as f:
        json.dump(content, f)


def load_version(filename: str) -> dict[str, Any] | None:
    try:
        with open(filename) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_description_version(course_id: int, description: str) -> None:
    versions = load_version("description_versions.json") or {}
    versions[str(course_id)] = {"content": description}
    save_version(versions, "description_versions.json")


def save_files_version(course_id: int, files: list[dict[str, str]]) -> None:
    versions = load_version("files_versions.json") or {}
    versions[str(course_id)] = {"content": files}
    save_version(versions, "files_versions.json")


def load_description_version(course_id: int) -> str:
    versions = load_version("description_versions.json") or {}
    course_data = versions.get(str(course_id), {})
    return course_data.get("content", "")


def load_files_version(course_id: int) -> list[dict[str, str]]:
    versions = load_version("files_versions.json") or {}
    course_data = versions.get(str(course_id), {})
    return course_data.get("content", [])


def diff_description(old_description: str, new_description: str) -> tuple[str, str]:
    """Use AI to analyze description changes and generate notification title and body."""

    if not old_description and not new_description:
        return (
            "New Course Created",
            "A new course has been created. Check the course page for details.",
        )
    if not old_description:
        return (
            "New Description Added",
            "Description has been added. Check the course page for details.",
        )
    if not new_description:
        return "Description Removed", "The course description has been removed."

    try:
        if not USE_OPENAI:
            raise ValueError("OpenAI usage is disabled")

        prompt = f"""A course description has been updated. Analyze the changes and generate a concise notification title (max 50 chars) and body (max 200 chars) that highlights what changed for students.

OLD DESCRIPTION:
{old_description}

NEW DESCRIPTION:  
{new_description}

Focus on important changes like deadlines, requirements, content updates, etc. Return in this exact format:
TITLE: [your title here]
BODY: [your body here]"""

        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=200,
            temperature=0.3,
        )

        content = response.choices[0].message.content

        if not content:
            raise ValueError("AI response is empty")

        # Parse the response
        lines = content.strip().split("\n")
        title = ""
        body = ""

        for line in lines:
            if line.startswith("TITLE:"):
                title = line.replace("TITLE:", "").strip()
            elif line.startswith("BODY:"):
                body = line.replace("BODY:", "").strip()

        # Fallback if parsing fails
        if not title or not body:
            raise ValueError("Failed to parse AI response", content)

        return title, body

    except Exception as e:
        print(f"⚠️  AI analysis failed: {e}")
        return (
            "Description Updated",
            f"Course description has been updated. Check the course page for details.",
        )


def diff_files(
    old_files: list[dict[str, str]], new_files: list[dict[str, str]]
) -> list[dict[str, str]]:
    old_set = {f["filename"]: f for f in old_files}
    new_set = {f["filename"]: f for f in new_files}

    added = [new_set[f] for f in new_set if f not in old_set]
    return added


def send_notification(
    title: str, body: str, category: str, url: str | None = None
) -> None:
    if not NOTIFICATION_ENDPOINT:
        return

    if not SEND_NOTIFICATIONS:
        print(f"🔕 Notifications are disabled.")
        print(f"Title: {title}")
        print(f"Body: {body}")
        print(f"Category: {category}")
        return

    payload = {"title": title, "body": body, "category": category}
    if url:
        payload["url"] = url

    # Retry configuration
    max_retries = 5
    base_delay = 1  # Start with 1 second
    max_delay = 300  # Maximum delay of 5 minutes

    for attempt in range(max_retries):
        try:
            print(
                f"📤 Sending notification (attempt {attempt + 1}/{max_retries}): {title}"
            )
            response = requests.post(
                NOTIFICATION_ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {NOTIFICATIONS_API_KEY}"},
                timeout=30,  # Add timeout to prevent hanging
            )
            response.raise_for_status()
            print(f"✅ Notification sent successfully: {title}")
            return  # Success! Exit the function

        except requests.RequestException as e:
            if attempt == max_retries - 1:  # Last attempt
                print(
                    f"❌ Failed to send notification after {max_retries} attempts: {title}"
                )
                print(f"   Final error: {e}")
                return

            # Calculate delay with exponential backoff
            delay = min(base_delay * (2**attempt), max_delay)
            print(f"⚠️  Attempt {attempt + 1} failed: {e}")
            print(f"🔄 Retrying in {delay} seconds...")
            time.sleep(delay)


def notify_description_change(
    course_code: str,
    course_name: str,
    course_url: str,
    old_description: str,
    new_description: str,
) -> None:
    title, body = diff_description(old_description, new_description)
    send_notification(
        f"({course_code}) {course_name} - {title}", body, "cms-description", course_url
    )


def notify_files_change(
    course_code: str,
    course_name: str,
    course_url: str,
    old_files: list[dict[str, str]],
    new_files: list[dict[str, str]],
) -> None:
    added_files = diff_files(old_files, new_files)
    for file in added_files:
        send_notification(
            f"({course_code}) {course_name} - New file just dropped",
            f"{file['filename']} ({file['category']})",
            "cms-files",
            course_url,
        )


# Main monitoring loop
print("🔍 Starting CMS notifier...")
courses = fetch_all_courses()

if not courses:
    exit("❌ No courses found")


# Get the season ID from the first course (they should all be from the same season)
season_id = courses[0][3]
print(f"📚 Monitoring {len(courses)} courses for season {season_id}")

while True:
    for course_code, course_name, course_id, season_id in courses:
        try:
            print(f"🔄 Checking ({course_code}) {course_name}...")

            course_url = f"https://cms.guc.edu.eg/apps/student/CourseViewStn.aspx?id={course_id}&sid={season_id}"
            current_page = fetch_page(course_url)

            new_description = parse_description(current_page)
            new_files = parse_files(current_page)

            old_description = load_description_version(course_id)
            old_files = load_files_version(course_id)

            if new_description and old_description != new_description:
                save_description_version(course_id, new_description)
                notify_description_change(
                    course_code,
                    course_name,
                    course_url,
                    old_description,
                    new_description,
                )
                print(f"📝 Description changed for ({course_code}) {course_name}")

            if new_files and old_files != new_files:
                save_files_version(course_id, new_files)
                notify_files_change(
                    course_code, course_name, course_url, old_files, new_files
                )
                print(f"📁 Files changed for ({course_code}) {course_name}")

        except Exception as e:
            print(f"❌ Error checking ({course_code}) {course_name}: {e}")
            continue

    print(f"💤 Sleeping for {POLLING_INTERVAL} seconds...")
    time.sleep(POLLING_INTERVAL)
