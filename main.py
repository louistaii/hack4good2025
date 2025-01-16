from flask import Flask, render_template, session, jsonify, request, redirect, url_for
from flask_session import Session
import flaskwebgui
import pathlib
import api_data
from transformers import T5Tokenizer, T5ForConditionalGeneration
import torch
from datetime import datetime, timedelta
import threading
import os

#setting path for files
path = pathlib.Path(__file__).parent.resolve()

#setup flask
app = Flask(__name__, template_folder=f'{path}/frontend')
gui = flaskwebgui.FlaskUI(app=app, server="flask", width=1500, height=1000)
app.secret_key = "your_secret_key"
app.config["SESSION_TYPE"] = "filesystem"
Session(app)



# Global variables to store the initialized resources
tokenizer = None
model = None
device = None
access_token = None

# Flags to track initialization status
llm_initialized = False
api_initialized = False

def setup_llm():
    global tokenizer, model, llm_initialized, device
    print("Initializing LLM...")
    tokenizer = T5Tokenizer.from_pretrained("google/flan-t5-large")
    model = T5ForConditionalGeneration.from_pretrained("google/flan-t5-large")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    llm_initialized = True
    print("LLM initialization complete.")

def setup_api():
    global access_token, api_initialized
    print("Initializing API...")
    access_token = api_data.login(force_reauth=False) 
    api_initialized = True
    print("API initialization complete.")

def LLM(prompt, max_length,min_length,length_penalty):
    if not tokenizer: return
    # Tokenize the input text
    inputs = tokenizer(prompt, return_tensors="pt").to(device)

    # Generate the output (summary)
    outputs = model.generate(
        inputs.input_ids, 
        max_length=max_length,  # Maximum length of the generated text
        min_length=min_length,  # Minimum length of the generated text
        length_penalty=length_penalty,  # Penalize long sentences
        num_beams=4,  # Use beam search for higher quality results
        early_stopping=True
    )
    result = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return(result)

def getquote():
    prompt = "fun fact related to books"
    return LLM(prompt, max_length=80,min_length=1,length_penalty=0)


##### MAIN PAGE ROUTES #####
quote = f"Fun fact: {getquote()}"
@app.route("/", methods=['GET', 'POST'])
def index():
    try:
        # Fetch to-do lists and tasks
        todo_data = api_data.fetchtodo(access_token)
        events = api_data.fetchcalender(access_token)
        formattedevents = []
        for event in events:
            formattedevents.append({
                'title': event['title'],
                'start': datetime.strptime(event['start'], '%Y-%m-%d %H:%M').isoformat(),
                'end': datetime.strptime(event['end'], '%Y-%m-%d %H:%M').isoformat()
            })
        quote = f"Fun fact: {getquote()}"
        return render_template("main.html", active_page = "home", todo_data=todo_data, events = formattedevents, quote=quote)
    except Exception as e:
        print(f"Error fetching to-do lists: {str(e)}")
        return render_template("error.html", error_message="Error fetching to-do lists.")
    

@app.route("/addtask", methods=["POST"])
def add_task():
    list_id = request.form.get('list_id')
    task_title = request.form.get('task_title')
    due_date = request.form.get('due_date')  # Format: YYYY-MM-DDTHH:MM
    
    if not due_date:
        due_date = None
    try:
        # Add the task
        api_data.add_todo(access_token, list_id, task_title, due_date)
        todo_data = api_data.fetchtodo(access_token)
        
        # Find the list and its newest task
        for list_data in todo_data:
            if list_data['list_id'] == list_id:
                # Get the most recently added not completed task
                newest_task = list_data['tasks'][0]['not_completed'][0] if list_data['tasks'][0]['not_completed'] else None
                if newest_task:
                    return jsonify({
                        'success': True,
                        'task': {
                            'id': newest_task['id'],
                            'title': newest_task['title'],
                            'due_date': newest_task['due_date']
                        }
                    })
        
        return jsonify({
            'success': False,
            'message': 'Task added but could not retrieve updated data'
        })
        
    except Exception as e:
        print(f"Error adding task: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        })
    
@app.route('/complete_task/<list_id>/<task_id>', methods=['POST'])
def complete_task(list_id, task_id):
    try:
        api_data.complete_todo(access_token, list_id, task_id)
        todo_data = api_data.fetchtodo(access_token)
        return jsonify({"success": True, "todo_data": todo_data}), 200
        
    except Exception as e:
        print(f"Error adding task: {str(e)}")
        return jsonify({"success": False, "error_message": str(e)}), 500
    

##### Email routes and helper functions #####
fetched_emails = {}

@app.route("/mail")
def email():
    try:
        # Calculate the time range: last 1 day
        end_time = datetime.utcnow()  # Current UTC time
        start_time = end_time - timedelta(days=1)  # 24 hours ago

        # Convert to ISO 8601 format
        end_time_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Fetch emails using your fetchmail function
        email_data = api_data.fetchmail(
            access_token,
            start_time_str,
            end_time_str,
            folder="inbox",
            top= 30,
            order_by="receivedDateTime desc"
        )
        
        #Store the emails in the global fetched_emails dictionary
        for email in email_data:
            fetched_emails[email['id']] = email  # Store email by its ID

        return render_template("mail.html", active_page = 'mail', email_data=email_data)
    
    except Exception as e:
        print(f"Error fetching emails: {str(e)}")
        return render_template("error.html", error_message="Error fetching emails.")

@app.route("/get_emails/<folder>")
def get_emails(folder):
    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=1)
        
        end_time_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        email_data = api_data.fetchmail(
            access_token,
            start_time_str,
            end_time_str,
            folder=folder.lower(),  # Use the folder parameter
            top=30,
            order_by="receivedDateTime desc"
        )
        print(folder.lower())
        # Store the emails in the global fetched_emails dictionary
        for email in email_data:
            fetched_emails[email['id']] = email

        return jsonify({"emails": email_data})
    
    except Exception as e:
        print(f"Error fetching emails: {str(e)}")
        print(folder.lower())
        return jsonify({"error": str(e)}), 500
    

@app.route('/summarize_email', methods=['POST'])
def summarize_email():
    print("called")
    try: 
        # Get the email ID from the request
        email_id = request.json.get('email_id')

        # Retrieve the email from the stored emails
        email_data = fetched_emails.get(email_id)

        if email_data is None:
            return jsonify({'error': 'Email not found'}), 404

        # Get the email body
        email_body = email_data.get('body', '')

        # Call the summarization function (this can be the LLM model you've set up)
        summary = LLM_summarize(email_body)  #Implement the summarize_text function

        return jsonify({'summary': summary})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def LLM_summarize(content):
    print("Summarizing...")
    if (content == ""):
        return("No text detected in email")
    # Input text for summarization
    input_text = f"Summarise this email:{content}"
    result = LLM(input_text,max_length=30,min_length=1,length_penalty=2)
    return(result)


@app.route('/generate_reply', methods=['POST'])
def generate_reply():
    try:
        email_id = request.json.get('email_id')
        email_data = fetched_emails.get(email_id)
        
        if email_data is None:
            return jsonify({'error': 'Email not found'}), 404
            
        email_body = email_data.get('body', '')
        
        # Use your existing LLM function but modify the prompt for reply generation
        input_text = f"""
        You received the following email. Please write a professional and concise reply, keeping the reply to pure text with no symbols or links.
        Email content: {email_body}"""
        reply = LLM(input_text,max_length=1500,min_length=50,length_penalty=1.5)
        print(f"generated reply:{reply}")
         
        return jsonify({'reply': reply})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    


@app.route('/send_email', methods=['POST'])
def send_email():
    try:
        data = request.get_json()
        
        # Validate required fields
        if not all(key in data for key in ['to', 'subject', 'body']):
            return jsonify({'error': 'Missing required fields'}), 400
        def parse_recipients(recipients):
            if isinstance(recipients, list):
                return [addr.strip() for addr in recipients if addr.strip()]
            elif isinstance(recipients, str):
                return [addr.strip() for addr in recipients.split(';') if addr.strip()]
            return []

        # Parse recipients using the helper function
        to_recipients = parse_recipients(data['to'])
        cc_recipients = parse_recipients(data.get('cc', ''))
        bcc_recipients = parse_recipients(data.get('bcc', ''))
        
        subject = data['subject']
        body = data['body']

        # Use the api_data.sendmail function
        api_data.sendmail(
            access_token=access_token,
            to_recipients=to_recipients,
            subject=subject,
            body=body,
            cc_recipients=cc_recipients,
            bcc_recipients=bcc_recipients
        )
        
        # If this was a draft, delete it
        if data.get('draftId'):
            try:
                api_data.delete_draft(access_token, data['draftId'])
            except Exception as e:
                print(f"Error deleting draft: {str(e)}")
        
        return jsonify({'success': True})
    
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return jsonify({'error': str(e)}), 500



@app.route('/save_draft', methods=['POST'])
def save_draft():
    try:
        data = request.get_json()
        
        # Parse recipients
        to_recipients = [{'emailAddress': {'address': addr.strip()}} 
                        for addr in data['to'].split(';') if addr.strip()]
        
        cc_recipients = [{'emailAddress': {'address': addr.strip()}} 
                        for addr in data['cc'].split(';') if addr.strip()]
        
        bcc_recipients = [{'emailAddress': {'address': addr.strip()}} 
                         for addr in data['bcc'].split(';') if addr.strip()]

        # Prepare draft message
        subject = data['subject']
        body = {
            'contentType': 'Text',
            'content': data['body']
        }

        if data.get('draftId'):
            # Update existing draft
            api_data.update_draft(
                access_token=access_token,
                draft_id=data['draftId'],
                subject=subject,
                body=body,
                to_recipients=to_recipients,
                cc_recipients=cc_recipients,
                bcc_recipients=bcc_recipients
            )
            draft_id = data['draftId']
        else:
            # Create new draft
            draft_id = api_data.create_draft(
                access_token=access_token,
                subject=subject,
                body=body,
                to_recipients=to_recipients,
                cc_recipients=cc_recipients,
                bcc_recipients=bcc_recipients
            )

        return jsonify({
            'success': True,
            'draftId': draft_id
        })
    
    except Exception as e:
        print(f"Error saving draft: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_draft/<draft_id>', methods=['GET'])
def get_draft(draft_id):
    try:
        # Get draft message using api_data module
        draft = api_data.get_draft(access_token, draft_id)
        
        # Format recipients from the draft data
        to_addresses = [r['emailAddress']['address'] 
                       for r in draft.get('toRecipients', [])]
        cc_addresses = [r['emailAddress']['address'] 
                       for r in draft.get('ccRecipients', [])]
        bcc_addresses = [r['emailAddress']['address'] 
                        for r in draft.get('bccRecipients', [])]

        draft_data = {
            'to': '; '.join(to_addresses),
            'cc': '; '.join(cc_addresses),
            'bcc': '; '.join(bcc_addresses),
            'subject': draft.get('subject', ''),
            'body': draft.get('body', {}).get('content', '')
        }

        return jsonify({
            'success': True,
            'draft': draft_data
        })
    
    except Exception as e:
        print(f"Error loading draft: {str(e)}")
        return jsonify({'error': str(e)}), 500




##### CALENDAR ROUTES #####

@app.route('/calendar')
def calendar():
    try:
        # Fetch all calendar events with pagination
        calendar_data = api_data.fetchcalender(access_token=access_token)
        print(calendar_data)
        return render_template("calendar.html", active_page='calendar', events=calendar_data)
    except Exception as e:
        print(f"Error fetching calendar events: {str(e)}")
        return render_template("error.html", error_message="Error fetching calendar events.")

@app.route("/add_event", methods=["POST"])
def add_event():
    try:
        # Get form data
        subject = request.form.get('event_title')
        start_time = request.form.get('event_start')
        end_time = request.form.get('event_end')  # Capture both start and end times
        location = request.form.get('location', None)
        body = request.form.get('body', None)

        # Validate that both start_time and end_time are present
        if not start_time or not end_time:
            return jsonify({"error": "Start time and end time are required."}), 400

        # Format start and end times 
        start_time_dt = datetime.strptime(start_time, "%Y-%m-%dT%H:%M")
        end_time_dt = datetime.strptime(end_time, "%Y-%m-%dT%H:%M")
        start_time_iso = start_time_dt.strftime("%Y-%m-%dT%H:%M:%S")
        end_time_iso = end_time_dt.strftime("%Y-%m-%dT%H:%M:%S")

        # Prepare event data for Microsoft Graph API
        event_data = {
            "subject": subject,
            "start": {
                "dateTime": start_time_iso,
                "timeZone": "UTC"
            },
            "end": {
                "dateTime": end_time_iso,
                "timeZone": "UTC"
            }
        }

        if location:
            event_data["location"] = {
                "displayName": location
            }

        if body:
            event_data["body"] = {
                "content": body,
                "contentType": "text"
            }
        api_data.add_event(access_token, event_data)
        return redirect(url_for('calendar')) 
    
    except Exception as e:
        print(f"Error adding event: {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/delete_event/<event_id>", methods=["DELETE"])
def delete_event(event_id):
    try:
        # Call your API to delete the event by its ID
        api_data.delete_event(access_token, event_id)
        return jsonify({'message': 'Event deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route("/fetch_events")   
def fetch_events():
    try:
        # Fetch all calendar events with pagination
        calendar_data = api_data.fetchcalender(access_token=access_token)
        return jsonify(calendar_data)  # Return data as JSON
        
    except Exception as e:
        print(f"Error fetching calendar events: {str(e)}")
        return jsonify({"error": "Error fetching calendar events."}), 500



@app.route('/schedule-meeting', methods=['POST'])
def schedule_meeting():
    title = request.form.get('meeting_title')
    date = request.form.get('meeting_date')
    time = request.form.get('meeting_time')
    duration = int(request.form.get('meeting_duration'))
    attendees = request.form.get('meeting_attendees').split(',')

    # Convert date and time into ISO 8601 format
    start_time = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    end_time = start_time + timedelta(minutes=duration)

    # Prepare attendees list for Graph API
    attendees_list = [
        {'emailAddress': {'address': email.strip(), 'name': email.strip()}, 'type': 'required'}
        for email in attendees
    ]

    # Create the event payload
    event = {
        'subject': title,
        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'UTC'},
        'end': {'dateTime': end_time.isoformat(), 'timeZone': 'UTC'},
        'attendees': attendees_list,
        'location': {'displayName': 'Online Meeting'},
        'isOnlineMeeting': True,
        'onlineMeetingProvider': 'teamsForBusiness'
    }

    try:
        api_data.schedule_meeting(access_token,event)
        return jsonify({'message': 'Meeting scheduled successfully!'}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to schedule meeting.', 'details': str(e)}), 500


@app.route('/reminders')
def reminders():
    return render_template("reminders.html", active_page = 'reminders')

@app.route('/settings')
def settings():
    return render_template("settings.html", active_page = 'settings')

@app.route('/logout')
def logout():
    os.exit()


if __name__ == "__main__":
    llm_thread = threading.Thread(target=setup_llm)
    api_thread = threading.Thread(target=setup_api)

    llm_thread.start()
    api_thread.start()
    llm_thread.join()
    api_thread.join()

    if llm_initialized and api_initialized:
        gui.run()