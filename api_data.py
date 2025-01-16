from msal import ConfidentialClientApplication
import webbrowser
import httpx
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
import requests
import time

CLIENT_ID = "ADD YOURS HERE"
CLIENT_SECRET = "ADD YOURS HERE"
AUTHORITY = "https://login.microsoftonline.com/consumers/"
SCOPES = ["Tasks.ReadWrite", "Calendars.ReadWrite", "Mail.ReadWrite", "User.Read", "Mail.send", 'OnlineMeetings.ReadWrite']
REDIRECT_URI = "http://localhost:8000"
CACHE_FILE = "token_cache.json"


def clear_token_cache():
    """Clear the token cache to allow switching accounts."""
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
        print("Token cache cleared.")

class TokenManager:
    def __init__(self, cache_file=CACHE_FILE):
        self.cache_file = cache_file
        self.tokens = self._load_cache()
    
    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def save_cache(self, token_response):
        # Save the token response with an expiration timestamp
        if token_response and 'access_token' in token_response:
            self.tokens = {
                'access_token': token_response['access_token'],
                'refresh_token': token_response.get('refresh_token'),
                'expires_at': datetime.now().timestamp() + token_response.get('expires_in', 3600)
            }
            with open(self.cache_file, 'w') as f:
                json.dump(self.tokens, f)
    
    def get_cached_token(self):
        if not self.tokens:
            return None
            
        # Check if token is expired (with 5 minute buffer)
        if datetime.now().timestamp() + 300 > self.tokens.get('expires_at', 0):
            return None
            
        return self.tokens.get('access_token')


class AuthCodeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        print(f"Request received: {self.path}")  # Log the request path
        
        if '?code=' in self.path:
            auth_code = self.path.split('code=')[1].split('&')[0]
            print(f"Authorization code received: {auth_code}")  # Log the auth code
        
        if 'error' in self.path:
            error_description = self.path.split('error_description=')[1].split('&')[0]
            print(f"Error during authentication: {error_description}")
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Authentication successful! You can close this window.")
        

def get_access_token(app, token_manager):
    global auth_code
    
    # First try to get token from cache
    cached_token = token_manager.get_cached_token()
    if cached_token:
        return cached_token
    
    # If no cached token, try to get new token
    auth_code = None
    
    server = HTTPServer(('localhost', 8000), AuthCodeHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    auth_url = app.get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        prompt="select_account"
    )
    print("Opening browser for authentication...")
    print(f"Authorization URL: {auth_url}")  # Add logging to check the URL
    webbrowser.open(auth_url)
    
    
    timeout = time.time() + 60
    while auth_code is None and time.time() < timeout:
        time.sleep(1)
    
    server.shutdown()
    server.server_close()
    
    if auth_code is None:
        raise Exception("No authorization code received within timeout period")
    
    result = app.acquire_token_by_authorization_code(
        code=auth_code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    if "access_token" not in result:
        raise Exception(f"Error getting token: {result}")
    
    # Save the new token in cache
    token_manager.save_cache(result)
    
    return result["access_token"]

def login(force_reauth=False):
    if force_reauth:
        clear_token_cache()
        

    token_manager = TokenManager()
    msal_app = ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY
    )

    if force_reauth:
        accounts = msal_app.get_accounts()
        if accounts:
            print("Cached accounts found:")
            for account in accounts:
                print(f"- {account['username']}")
                print("Clearing all cached accounts...")
                for account in accounts:
                    msal_app.remove_account(account)
            print("Cached accounts cleared.")
    
    try:
        #Get token (from cache if possible)
        access_token = get_access_token(msal_app, token_manager)
        return access_token
    except Exception as e:
        print(f"Error: {str(e)}")\
        
def fetchname(access_token):
    url = "https://graph.microsoft.com/v1.0/me"
    headers = {
        'Authorization': f'Bearer {access_token}',
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()

        # Try to get the display name directly
        user_name = data.get('surname', None)

        print(f"User Name: {user_name}")
        return user_name
    else:
        print("Error fetching data:", response.status_code, response.text)
        return "Error retrieving name"
    
    
def fetchmail(access_token, start_time, end_time, folder="inbox", subject_filter=None, top=5, order_by="receivedDateTime desc"):
    """
    Fetches emails from a specific folder within a time range, and optionally filtered by subject.
    :param access_token: The access token to authenticate with Microsoft Graph API.
    :param start_time: The start date (inclusive) in ISO format (YYYY-MM-DDTHH:MM:SS).
    :param end_time: The end date (inclusive) in ISO format (YYYY-MM-DDTHH:MM:SS).
    :param folder: The folder to fetch emails from (default is "inbox").
    :param subject_filter: Optional filter for the subject of the emails.
    :param top: The maximum number of emails to return (default is 5).
    :param order_by: The field to order the results by (default is "receivedDateTime desc").
    :return: A list of email details with their body content from the specified folder.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Build the query parameters
    query_params = []
    if subject_filter:
        query_params.append(f"subject eq '{subject_filter}'")
    if start_time and end_time:
        query_params.append(f"receivedDateTime ge {start_time} and receivedDateTime le {end_time}")
    if order_by:
        query_params.append(f"$orderby={order_by}")
    if top:
        query_params.append(f"$top={top}")
    
    # Construct URL to fetch emails from the specific folder
    folder_url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages"
    
    # Add the query parameters to the URL
    if query_params:
        folder_url += "?" + "&".join(query_params)
    
    # Send the request to Microsoft Graph API
    response = httpx.get(folder_url, headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"Error {response.status_code}: {response.text}")
    
    emails = response.json().get('value', [])
    
    # Extract email details
    email_details = []
    
    if emails:
        for email in emails:
            # Parse the email body (HTML) using BeautifulSoup to extract readable text
            body_html = email['body']['content']
            soup = BeautifulSoup(body_html, 'html.parser')
            body_text = soup.get_text(separator="\n", strip=True)  # Extract plain text

            # Store email data
            email_data = {
                'id': email['id'],
                'subject': email['subject'],
                'from': email['from']['emailAddress']['address'],
                'receivedDateTime': email['receivedDateTime'],
                'body': body_text  # Use the parsed plain text body
            }
            email_details.append(email_data)
    
    else:
        print(f"No emails found in the {folder} folder within the given time range.")
    
    return email_details

def sendmail(access_token, to_recipients, subject, body, cc_recipients=None, bcc_recipients=None, attachments=None):
    """
    Sends an email using Microsoft Graph API.
    :param access_token: The access token to authenticate with Microsoft Graph API.
    :param to_recipients: A list of recipient email addresses.
    :param subject: The email subject.
    :param body: The email body (in HTML or plain text).
    :param cc_recipients: Optional list of CC recipient email addresses.
    :param bcc_recipients: Optional list of BCC recipient email addresses.
    :param attachments: Optional list of attachments (each as a dictionary).
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    message = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body
            },
            "toRecipients": [{"emailAddress": {"address": email}} for email in to_recipients],
        },
        "saveToSentItems": "true"
    }
    
    if cc_recipients:
        message["message"]["ccRecipients"] = [{"emailAddress": {"address": email}} for email in cc_recipients]
    if bcc_recipients:
        message["message"]["bccRecipients"] = [{"emailAddress": {"address": email}} for email in bcc_recipients]
    if attachments:
        message["message"]["attachments"] = attachments

    url = "https://graph.microsoft.com/v1.0/me/sendMail"
    response = httpx.post(url, headers=headers, json=message)
    
    if response.status_code == 202:
        print("Email sent successfully.")
    else:
        print(f"Error {response.status_code}: {response.text}")


def save_draft(access_token, to_recipients, subject, body, cc_recipients=None, bcc_recipients=None, attachments=None):
    """
    Saves an email as a draft using Microsoft Graph API.
    :param access_token: The access token to authenticate with Microsoft Graph API.
    :param to_recipients: A list of recipient email addresses.
    :param subject: The email subject.
    :param body: The email body (in HTML or plain text).
    :param cc_recipients: Optional list of CC recipient email addresses.
    :param bcc_recipients: Optional list of BCC recipient email addresses.
    :param attachments: Optional list of attachments (each as a dictionary).
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    draft = {
        "subject": subject,
        "body": {
            "contentType": "HTML",
            "content": body
        },
        "toRecipients": [{"emailAddress": {"address": email}} for email in to_recipients],
    }
    
    if cc_recipients:
        draft["ccRecipients"] = [{"emailAddress": {"address": email}} for email in cc_recipients]
    if bcc_recipients:
        draft["bccRecipients"] = [{"emailAddress": {"address": email}} for email in bcc_recipients]
    if attachments:
        draft["attachments"] = attachments

    url = "https://graph.microsoft.com/v1.0/me/messages"
    response = httpx.post(url, headers=headers, json=draft)
    
    if response.status_code == 201:
        print("Draft saved successfully.")
    else:
        print(f"Error {response.status_code}: {response.text}")

def create_draft(access_token, subject, body, to_recipients, cc_recipients=None, bcc_recipients=None):
    """Create a new draft email"""
    endpoint = 'https://graph.microsoft.com/v1.0/me/messages'
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    message = {
        'subject': subject,
        'body': body,
        'toRecipients': to_recipients,
        'ccRecipients': cc_recipients or [],
        'bccRecipients': bcc_recipients or []
    }
    
    response = requests.post(endpoint, headers=headers, json=message)
    response.raise_for_status()
    return response.json().get('id')

def update_draft(access_token, draft_id, subject, body, to_recipients, cc_recipients=None, bcc_recipients=None):
    """Update an existing draft email"""
    endpoint = f'https://graph.microsoft.com/v1.0/me/messages/{draft_id}'
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    message = {
        'subject': subject,
        'body': body,
        'toRecipients': to_recipients,
        'ccRecipients': cc_recipients or [],
        'bccRecipients': bcc_recipients or []
    }
    
    response = requests.patch(endpoint, headers=headers, json=message)
    response.raise_for_status()

def get_draft(access_token, draft_id):
    """Get a draft email by ID"""
    endpoint = f'https://graph.microsoft.com/v1.0/me/messages/{draft_id}'
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    response = requests.get(endpoint, headers=headers)
    response.raise_for_status()
    return response.json()

def delete_draft(access_token, draft_id):
    """Delete a draft email"""
    endpoint = f'https://graph.microsoft.com/v1.0/me/messages/{draft_id}'
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    response = requests.delete(endpoint, headers=headers)
    response.raise_for_status()


def fetchtodo(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Fetch the to-do lists
    response = httpx.get("https://graph.microsoft.com/v1.0/me/todo/lists", headers=headers)
    if response.status_code != 200:
        raise Exception(f"Error {response.status_code}: {response.text}")
    
    todo_lists = response.json().get('value', [])
    all_lists_data = []

    if todo_lists:
        for todo_list in todo_lists:
            list_data = {"list_name": todo_list['displayName'], "list_id": todo_list['id'], "tasks": []}


            # Now, fetch the tasks within this to-do list
            list_id = todo_list['id']
            tasks_url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks"
            tasks_response = httpx.get(tasks_url, headers=headers)
            
            if tasks_response.status_code != 200:
                print(f"Error fetching tasks for list '{todo_list['displayName']}': {tasks_response.status_code}")
                continue
            
            tasks = tasks_response.json().get('value', [])
            
            if tasks:
                # Separate completed and not completed tasks
                completed_tasks = []
                not_completed_tasks = []
                
                for task in tasks:
                    # Safely access dueDateTime and avoid KeyError
                    due_date = task.get('dueDateTime', {}).get('dateTime', 'No due date')
                    
                    if due_date != 'No due date':
                        try:
                            due_date = datetime.fromisoformat(due_date)
                            due_date = due_date.strftime('%b %d, %Y %I:%M %p')  # Format to "Jan 15, 2025 05:00 PM"
                        except ValueError:
                            due_date = 'Invalid date format'
                            
                    task_data = {
                        'id': task['id'],
                        'title': task['title'],
                        'status': task['status'],
                        'due_date': due_date
                    }
                    
                    if task['status'] == 'completed':
                        completed_tasks.append(task_data)
                    else:
                        not_completed_tasks.append(task_data)

                # Add tasks to list data
                list_data['tasks'].append({
                    'not_completed': not_completed_tasks,
                    'completed': completed_tasks
                })

            all_lists_data.append(list_data)

    return all_lists_data



def add_todo(access_token, list_id, task_title, due_date=None):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Create the new task data
    task_data = {
        "title": task_title,
        "dueDateTime": {
            "dateTime": due_date,  # Format: "YYYY-MM-DDTHH:MM:SS"
            "timeZone": "UTC"  # Time zone for the due date (optional, can adjust as needed)
        } if due_date else None
    }
    
    url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks"
    response = httpx.post(url, headers=headers, json=task_data)
    
    if response.status_code == 201:
        print(f"Task '{task_title}' successfully added to list.")
    else:
        print(f"Error {response.status_code}: {response.text}")



def complete_todo(access_token, list_id, task_id):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Check if list_id and task_id are valid before proceeding
    if not list_id or not task_id:
        raise ValueError(f"Invalid list_id or task_id: list_id={list_id}, task_id={task_id}")

    # Update the task's status to completed
    task_data = {
        "status": "completed"
    }

    url = f"https://graph.microsoft.com/v1.0/me/todo/lists/{list_id}/tasks/{task_id}"
    response = httpx.patch(url, headers=headers, json=task_data)

    if response.status_code == 200:
        print(f"Task '{task_id}' in list '{list_id}' successfully marked as completed.")
    else:
        print(f"Error {response.status_code}: {response.text} - URL: {url}")



def fetchcalender(access_token, start_time=None, end_time=None, order_by="start/dateTime asc"):
    """
    Fetch calendar events within a time range.
    :param access_token: The access token to authenticate with Microsoft Graph API.
    :param start_time: The start date (inclusive) in ISO format (YYYY-MM-DDTHH:MM:SS).
    :param end_time: The end date (inclusive) in ISO format (YYYY-MM-DDTHH:MM:SS).
    :param top: The maximum number of events to return (default is 5).
    :param order_by: The field to order the results by (default is "start/dateTime asc").
    :return: A list of calendar events.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Build the query parameters
    query_params = []
    query_params.append(f"start/dateTime ge {start_time}")
    query_params.append(f"end/dateTime le {end_time}")
    query_params.append(f"$orderby={order_by}")
    
    # Construct URL to fetch calendar events
    calendar_url = "https://graph.microsoft.com/v1.0/me/events"
    
    # Add the query parameters to the URL
    if query_params:
        calendar_url += "?" + "&".join(query_params)
    
    # Send the request to Microsoft Graph API
    response = httpx.get(calendar_url, headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"Error {response.status_code}: {response.text}")
    
    events = response.json().get('value', [])

    formatted_events = []
    for event in events:
        title = event.get('subject', 'No title')
        
        # Format start and end times
        start = event.get('start', {}).get('dateTime', '')
        end = event.get('end', {}).get('dateTime', '')
        
        # Convert dateTime to a human-readable format (YYYY-MM-DD HH:MM)
        if start:
            start_time = datetime.fromisoformat(start[:-1]).strftime('%Y-%m-%d %H:%M')
        else:
            start_time = ''
        
        if end:
            end_time = datetime.fromisoformat(end[:-1]).strftime('%Y-%m-%d %H:%M')
        else:
            end_time = ''
        
        formatted_events.append({
            'id': event.get('id', ''),
            'title': title,
            'start': start_time,
            'end': end_time
        })
    
    return formatted_events



def add_event(access_token, event_data):
    """
    Adds a new event to the calendar.
    :param access_token: The access token to authenticate with Microsoft Graph API.
    :param event_data: The data for the event (subject, start, end, location, body).
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    url = "https://graph.microsoft.com/v1.0/me/events"
    response = httpx.post(url, headers=headers, json=event_data)
    
    if response.status_code == 201:
        print(f"Event '{event_data['subject']}' successfully added to calendar.")
    else:
        print(f"Error {response.status_code}: {response.text}")


def delete_event(access_token, event_id):
    """
    Deletes an event from the calendar.
    :param access_token: The access token to authenticate with Microsoft Graph API.
    :param event_id: The ID of the event to delete.
    """
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    url = f"https://graph.microsoft.com/v1.0/me/events/{event_id}"
    response = httpx.delete(url, headers=headers)
    
    if response.status_code == 204:
        print(f"Event with ID '{event_id}' successfully deleted from calendar.")
    else:
        print(f"Error {response.status_code}: {response.text}")


def schedule_meeting(access_token, event):
    """
    Schedules an online meeting using the Microsoft Graph API.

    Args:
        access_token (str): The access token for the authenticated user.
        subject (str): The subject of the meeting.
        start_time (str): The start time of the meeting in ISO 8601 format (e.g., '2024-07-05T14:00:00Z').
        end_time (str): The end time of the meeting in ISO 8601 format (e.g., '2024-07-05T15:00:00Z').
        attendees (list): A list of dictionaries, where each dictionary represents an attendee with keys 'emailAddress' and 'type'.

    Returns:
        dict: The response from the Microsoft Graph API, or None if an error occurred.
    """

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    url = "https://graph.microsoft.com/v1.0/me/events"

    try:
        response = requests.post(url, headers=headers, json= event)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error scheduling meeting: {e}")
        return None