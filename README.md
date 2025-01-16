# Hack4good 2025

Free to use Personal Assitant made for Singapore Book Council.

## Table of Contents

- [Installation](#installation)
- [Usage](#usage)
- [Features](#features)
- [License](#license)

## Installation

To install the project, follow these steps:

1. Clone the repository:
   ```bash
   git clone https://github.com/louistaii/project-name.git
   ```
2. Navigate into the project directory
3. Install the required dependencies
   ```bash
   pip install -r requirements.txt
   ```
4. Install [CUDA](https://developer.nvidia.com/cuda-downloads/) and [Pytorch](https://pytorch.org/) that best suits your device

## Usage
1. Obtain a FREE [Microsoft graph API](https://portal.azure.com/#home) Client ID and Client Secret
2. Ensure API is given the needed permissions 
    - Calendars.ReadWrite
    - Mail.ReadWrite
    - Mail.Send
    - OnlineMeetings.ReadWrite
    - Tasks.ReadWrite
    - User.Read
3. Replace CLIENT_ID and CLIENT_SECRET in api_data.py with your own
4. Simply run main.py with your favourite debugger or do
  ```bash
  python main.py
  ```
5. Initial run will take a while longer due to the downloading of google/flan-T5-Large (~3GB). Please be patient!

## Features
### 1. Calendar Integration:
- View, add, and delete events from your Outlook calendar
- Automatically schedule and arrange meetings with calendar invites

### 2. To-Do List Management:
- Sync with Microsoft To Do
- View, add, and complete tasks directly from the assistant

### 3. Email Integration:
- Access Outlook mail to view, draft, and send emails
- AI-powered email summaries and smart replies

### 4. AI-Powered book-realted Fun Facts
   
## License
This project is licensed under the MIT License - see the LICENSE file for details.
