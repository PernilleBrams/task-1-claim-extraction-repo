import streamlit as st
import pandas as pd
import gspread
import datetime
import os
import threading
from google.oauth2.service_account import Credentials
import json

# --- GOOGLE SHEETS SETUP ---
GOOGLE_CREDENTIALS = st.secrets["GOOGLE_CREDENTIALS"]
SHEET_ID = st.secrets["SHEET_ID"]

# Authenticate Google Sheets
creds = Credentials.from_service_account_info(GOOGLE_CREDENTIALS, scopes=["https://www.googleapis.com/auth/spreadsheets"])
gc = gspread.authorize(creds)

# --- GOOGLE SHEETS FUNCTIONS ---
def fetch_allowed_users():
    """Fetch allowed users from the 'allowed_users' tab in the connected Google Sheet."""
    spreadsheet = gc.open_by_key(SHEET_ID)
    worksheet = spreadsheet.worksheet("allowed_users_CE")  # Use the new tab name
    allowed_users = worksheet.col_values(1)  # Fetch usernames from Column A
    return set(allowed_users)

def get_user_worksheet(user_id):
    """ Ensure each user has a personal worksheet. Create one if it doesn’t exist. """
    spreadsheet = gc.open_by_key(SHEET_ID)
    try:
        return spreadsheet.worksheet(user_id)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=user_id, rows="1000", cols="4")
        worksheet.insert_row(["user_id", "sentence", "annotation", "time_of_annotation"], index=1)
        return worksheet

def get_annotated_sentences(user_id):
    """ Fetch already annotated sentences for the user. """
    worksheet = get_user_worksheet(user_id)
    data = worksheet.get_all_values()
    if len(data) > 1:
        df_annotations = pd.DataFrame(data[1:], columns=["user_id", "sentence", "annotation", "time_of_annotation"])
        return set(df_annotations["sentence"].tolist())
    return set()

def save_annotations(user_id, annotations):
    """ Save annotations asynchronously to Google Sheets. """
    worksheet = get_user_worksheet(user_id)
    worksheet.append_rows(annotations)

# --- STREAMLIT APP SETUP ---
st.sidebar.title("Brugerlogin")

# ✅ Load allowed users dynamically from Google Sheets
# ALLOWED_USERS = fetch_allowed_users()

# ✅ Load allowed users only once per session
if "ALLOWED_USERS" not in st.session_state:
    st.session_state.ALLOWED_USERS = fetch_allowed_users()

# ✅ Check if user is logged in
if "user_id" not in st.session_state:
    user_id = st.sidebar.text_input("Indtast dit bruger-ID:")
    if st.sidebar.button("Log in") and user_id.strip():
        #if user_id.strip() in ALLOWED_USERS:
        if user_id.strip() in st.session_state.ALLOWED_USERS:
            st.session_state.user_id = user_id.strip()
            st.session_state.sentence_index = -1
            st.session_state.annotations = []
            st.session_state.annotated_sentences = get_annotated_sentences(user_id)
            st.session_state.worksheet_ready = False
            st.session_state.finished = False
            st.session_state.selected_label = None  # ✅ Track selected button label
            st.rerun()
        else:
            st.sidebar.error("❌ Adgang nægtet: Dit bruger-ID er ikke autoriseret.")
else:
    user_id = st.session_state.user_id
    st.sidebar.success(f"✅ Du er logget ind som: **{user_id}**")

    if st.sidebar.button("Log ud"):
        if st.session_state.annotations:
            threading.Thread(target=save_annotations, args=(user_id, st.session_state.annotations), daemon=True).start()
            st.session_state.annotations = []
        st.session_state.clear()
        st.rerun()

# 🚨 Block annotation until user logs in
if "user_id" not in st.session_state:
    st.warning("Indtast dit bruger-ID ude til venstre for at begynde at annotere.")
    st.stop()

# ✅ Ensure each user has their personal worksheet (but do not block UI)
if not st.session_state.get("worksheet_ready", False):
    threading.Thread(target=get_user_worksheet, args=(user_id,), daemon=True).start()
    st.session_state.worksheet_ready = True

# --- LOAD SENTENCES FROM LOCAL FILE ---
BASE_DIR = os.getcwd()
DATA_FILE = os.path.join(BASE_DIR, "data", "clean", "processed_sentences.txt")

if not os.path.exists(DATA_FILE):
    st.error("Processed sentence file missing! Run `preprocess.py` first.")
    st.stop()

with open(DATA_FILE, "r", encoding="utf-8") as file:
    sentences = [line.strip() for line in file if line.strip()]

df_sentences = pd.DataFrame(sentences, columns=["sentence"])

# ✅ Remove already annotated sentences from the dataset
unannotated_sentences = df_sentences[~df_sentences["sentence"].isin(st.session_state.annotated_sentences)]["sentence"].tolist()

# ✅ Store unannotated sentences in session state
st.session_state.unannotated_sentences = unannotated_sentences

# Initialize progress and ticket tracking
if "total_sentences" not in st.session_state:
    st.session_state.total_sentences = len(st.session_state.unannotated_sentences)

if "annotated_count" not in st.session_state:
    st.session_state.annotated_count = len(st.session_state.annotated_sentences)

if "lottery_tickets" not in st.session_state:
    st.session_state.lottery_tickets = st.session_state.annotated_count // 30

# ✅ Ensure `sentence_index` is initialized correctly
if "sentence_index" not in st.session_state or st.session_state.sentence_index == -1:
    st.session_state.sentence_index = 0
    #st.rerun()

# ✅ If all sentences are annotated, trigger completion message immediately
if len(st.session_state.unannotated_sentences) == 0 or st.session_state.get("finished", False):
    st.session_state.finished = True
    st.success("🎉 Du har annoteret alle sætninger!")
    st.info("✅ Du kan nu logge ud via knappen i sidebaren.")
    
    # ✅ Save any remaining annotations on completion
    if st.session_state.annotations:
        threading.Thread(target=save_annotations, args=(user_id, st.session_state.annotations), daemon=True).start()
        st.session_state.annotations = []

    st.stop()

# ✅ Get the next sentence properly
sentence = st.session_state.unannotated_sentences[st.session_state.sentence_index]

# --- SENTENCE DISPLAY (Styled Like Screenshot) ---
# --- Detect Dark Mode ---
is_dark_mode = st.get_option("theme.base") == "dark"

# Set colors dynamically
bg_color = "#f9f9f9" if not is_dark_mode else "#262730"  # Light gray for light mode, dark gray for dark mode
text_color = "#000000" if not is_dark_mode else "#ffffff"  # Black for light mode, white for dark mode

# --- Progress Bar ---
progress = st.session_state.annotated_count / st.session_state.total_sentences
st.progress(progress)

# --- Lottery Ticket Counter ---
st.info(f"🎟️ Lodsedler: {st.session_state.lottery_tickets} (Optjen en ny lodseddel for hver 30. annoterede sætning)")

# --- SENTENCE DISPLAY (Styled for Both Modes) ---
st.markdown(
    f"""
    <div style="border:2px solid #ccc; padding:15px; margin:15px 0; background-color:{bg_color}; 
                font-size:18px; font-weight:bold; color:{text_color}; padding:10px;">
        {sentence}
    </div>
    """,
    unsafe_allow_html=True,
)

# --- More Context Button ---
st.button("Mere kontekst", key="context_btn")

# --- Question Text ---
st.markdown("**Vil den brede offentlighed være interesseret i at vide, om (dele af) denne sætning er sand eller falsk?**")

# --- FUNCTION TO HANDLE ANNOTATION ---
def annotate(label):
   
    # Get the current sentence
    sentence = st.session_state.unannotated_sentences[st.session_state.sentence_index]

    # Store annotation in session state
    new_entry = [user_id, sentence, label, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
    st.session_state.annotations.append(new_entry)

    # Update progress for user
    st.session_state.annotated_count += 1

    # Aware lottery ticket for every 30 annotations
    if st.session_state.annotated_count % 30 == 0:
        st.session_state.lottery_tickets += 1
        st.success(f"🎉 Du har optjent en ekstra lodseddel! Antal lodsedler: {st.session_state.lottery_tickets}")

    # ✅ Move to next sentence or show completion message
    if st.session_state.sentence_index >= len(st.session_state.unannotated_sentences) - 1:
        st.session_state.finished = True
        threading.Thread(target=save_annotations, args=(user_id, st.session_state.annotations), daemon=True).start()
        st.session_state.annotations = []
        st.rerun()
    else:
        st.session_state.sentence_index += 1
        if len(st.session_state.annotations) >= 10:
            threading.Thread(target=save_annotations, args=(user_id, st.session_state.annotations), daemon=True).start()
            st.session_state.annotations = []
        st.rerun()

def skip_sentence():
    """ Move to the next sentence without annotation. """
    if st.session_state.sentence_index < len(st.session_state.unannotated_sentences) - 1:
        st.session_state.sentence_index += 1
        st.rerun()
    else:
        st.session_state.finished = True
        st.success("🎉 Du har annoteret alle sætninger!")
        st.info("✅ Du kan nu logge ud via knappen i sidebaren.")
        st.stop()
        
# --- ANNOTATION BUTTONS ---
if st.button("Der er **ikke** en faktuel påstand.", key=f"label_btn_{st.session_state.sentence_index}_1"):
    annotate("No factual claim")

if st.button("Der er en faktuel påstand, men den er **ikke vigtig**.", key=f"label_btn_{st.session_state.sentence_index}_2"):
    annotate("Factual but unimportant")

if st.button("Der er en **vigtig** faktuel påstand.", key=f"label_btn_{st.session_state.sentence_index}_3"):
    annotate("Important factual claim")

if st.button("Det er en **normativ** udtalelse (værdi-udtalelse, ønske eller anbefaling)", key=f"label_btn_{st.session_state.sentence_index}_4"):
    annotate("Normative statement")

## Labels
# No factual claim – No verifiable information.
# Factual but unimportant claim – Verifiable but not impactful.
# Important factual claim – Verifiable and relevant.
# Normative statement – Expresses value judgments, recommendations, or policies.
# Maybe also: Mixed claim – Contains both factual and normative elements (optional but useful for edge cases).

# --- SEPARATOR LINE ---
st.markdown("---")  # Adds a horizontal line separator
        
# --- SKIP BUTTON (Styled with Smaller Font) ---
skip_button_style = """
    <style>
    .small-font-button > button {
        font-size: 12px !important;
        padding: 4px 10px !important;
    }
    </style>
"""
st.markdown(skip_button_style, unsafe_allow_html=True)

# Place the button with custom styling
with st.container():
    if st.button("Spring denne sætning over", key=f"skip_{st.session_state.sentence_index}"):
        skip_sentence()
        

# def go_back():
#     """ Move back one sentence to allow editing. """
#     if st.session_state.sentence_index > 0:
#         st.session_state.sentence_index -= 1
#         st.rerun()

# --- BOTTOM ACTION BUTTONS ---
#col1, col2 = st.columns([1, 2])

#with col1:
#    if st.button("Spring denne sætning over", key=f"skip_{st.session_state.sentence_index}"):
#        skip_sentence()

# with col2:
#     if st.button("Rediger tidligere svar", key="modify_btn"):
#         go_back()
