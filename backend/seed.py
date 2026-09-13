"""
seed.py
-------
1. Creates all tables (safe to re-run).
2. Creates the admin account from ADMIN_USERNAME / ADMIN_PASSWORD in .env.
3. Seeds all three fictional cases — CT-2074, IN-1042, WF-2203 — each with
   its evidence, suspects, questions, and hints. All data is fictional,
   written for a college tech-fest competition. No real hacking techniques,
   credentials, or systems are involved.

Trimmed assessment: 35 questions total across the three cases (12 + 12 + 11),
combined score out of 100 (34 + 33 + 33).

Every case now runs for 45 minutes (standardized), and teams are NOT
assigned a single case — they can attempt all three, in any order, once an
admin creates the team (see routers/admin.py).

Run with:  python seed.py   (from inside backend/, with your .env set up)
"""
from database import Base, engine, SessionLocal
from config import settings
from security import hash_password
import models as m


def seed_admin(db):
    existing = db.query(m.User).filter(m.User.username == settings.ADMIN_USERNAME, m.User.role == "admin").first()
    if existing:
        print(f'[seed] Admin "{settings.ADMIN_USERNAME}" already exists — skipping.')
        return
    db.add(m.User(
        team_id=None, full_name="Platform Admin", username=settings.ADMIN_USERNAME,
        password_hash=hash_password(settings.ADMIN_PASSWORD), role="admin",
    ))
    db.commit()
    print(f'[seed] Admin account created — username: "{settings.ADMIN_USERNAME}" (use the password from your .env).')


def _seed_case(db, case_kwargs, evidence_by_type, suspects, questions, hints):
    existing = db.query(m.Case).filter(m.Case.case_code == case_kwargs["case_code"]).first()
    if existing:
        print(f'[seed] Case {case_kwargs["case_code"]} already exists — skipping.')
        return existing

    case = m.Case(**case_kwargs)
    db.add(case)
    db.flush()

    for etype, items in evidence_by_type.items():
        for i, item in enumerate(items):
            db.add(m.Evidence(case_id=case.id, evidence_type=etype, title=item["title"], content=item["content"], display_order=i))

    for s in suspects:
        db.add(m.Suspect(case_id=case.id, name=s["name"], role=s["role"], description=s["description"]))

    for i, q in enumerate(questions):
        options = q["options"]
        assert len(options) == 8, f'Question "{q["question"][:40]}" must have exactly 8 options, got {len(options)}.'
        correct_option = q["correct_option"]
        assert 0 <= correct_option < 8, f'Question "{q["question"][:40]}" correct_option out of range.'
        db.add(m.Question(case_id=case.id, round_name=q["round_name"], question=q["question"],
                           correct_answer=options[correct_option], options=options, correct_option=correct_option,
                           marks=q["marks"], display_order=i))

    for h in hints:
        db.add(m.Hint(case_id=case.id, round_name=h["round_name"], hint_text=h["hint_text"], penalty=h["penalty"]))

    db.commit()
    print(f'[seed] Case {case_kwargs["case_code"]} seeded ({case_kwargs["title"]}) — '
          f'{len(questions)} questions, {sum(q["marks"] for q in questions)} pts.')
    return case


def seed_ct2074(db):
    case_kwargs = dict(
        case_code="CT-2074", title="The Missing ₹75,000",
        description="A simulated loss of ₹75,000 was reported from a fictional account. Investigate the digital "
                     "evidence trail to reconstruct the attack. All data in this case is fictional and created "
                     "for a college tech-fest competition.",
        victim_name="Aarav Sharma", financial_loss=75000, duration_minutes=45, active=True,
        correct_suspect="Vikram Shah",
        correct_attack_method="Phishing email led to credential compromise and unauthorized login",
        correct_attack_time="08:16",
        correct_evidence_order="email,browser,login,transaction",
    )

    evidence = {
        "email": [
            {"title": "URGENT — Account Verification Required", "content": {"from": "security-alert@secure-example.test", "subject": "URGENT — Account Verification Required", "time": "08:12 AM", "body": "Your account will be locked. Click the link below to verify immediately.", "link": "http://account-check.example.test/verify", "suspicious": True}},
            {"title": "Your monthly statement is ready", "content": {"from": "no-reply@bank-example.test", "subject": "Your monthly statement is ready", "time": "07:40 AM", "body": "Your statement for last month is now available in your account.", "link": "https://mail.example.test/statements", "suspicious": False}},
            {"title": "Weekend Sale — 20% off", "content": {"from": "newsletter@shopping-example.test", "subject": "Weekend Sale — 20% off", "time": "07:55 AM", "body": "Don't miss our weekend sale on electronics.", "link": "https://shopping-example.test/sale", "suspicious": False}},
            {"title": "Re: Your recent request", "content": {"from": "support@secure-example.test", "subject": "Re: Your recent request", "time": "09:02 AM", "body": "Thank you for contacting support. Your ticket has been closed.", "link": None, "suspicious": False}},
            {"title": "Fest schedule update", "content": {"from": "hr@college-example.test", "subject": "Fest schedule update", "time": "06:50 AM", "body": "The tech fest schedule has been updated, please check the portal.", "link": "https://college-example.test/portal", "suspicious": False}},
        ],
        "login": [
            {"title": f"Login Record {i+1}", "content": c} for i, c in enumerate([
                {"time": "08:14", "device": "Chrome/Windows", "location": "Delhi", "status": "Failed"},
                {"time": "08:16", "device": "Chrome/Windows", "location": "Delhi", "status": "Success"},
                {"time": "08:22", "device": "Mobile Browser", "location": "Unknown", "status": "Success"},
                {"time": "08:31", "device": "Chrome/Windows", "location": "Delhi", "status": "Failed"},
                {"time": "07:45", "device": "Chrome/Windows", "location": "Delhi", "status": "Success"},
                {"time": "07:50", "device": "Chrome/Windows", "location": "Delhi", "status": "Success"},
                {"time": "08:40", "device": "Mobile Browser", "location": "Unknown", "status": "Success"},
                {"time": "08:45", "device": "Mobile Browser", "location": "Unknown", "status": "Success"},
                {"time": "09:00", "device": "Chrome/Windows", "location": "Delhi", "status": "Success"},
                {"time": "09:10", "device": "Chrome/Windows", "location": "Delhi", "status": "Success"},
            ])
        ],
        "browser": [
            {"title": f"Browser Entry {i+1}", "content": c} for i, c in enumerate([
                {"time": "08:05", "url": "news.example.test"},
                {"time": "08:10", "url": "mail.example.test"},
                {"time": "08:13", "url": "account-check.example.test"},
                {"time": "08:14", "url": "download.example.test"},
                {"time": "08:18", "url": "mail.example.test"},
            ])
        ],
        "chat": [
            {"title": f"Chat Log {i+1}", "content": c} for i, c in enumerate([
                {"time": "08:02", "person_a": "Did you receive the security email?", "person_b": "Yes."},
                {"time": "08:03", "person_a": "Don't ignore it. Check immediately.", "person_b": "Okay, checking now."},
                {"time": "08:15", "person_a": "It asked me to verify my account.", "person_b": "Did you enter your details?"},
                {"time": "08:17", "person_a": "Yes, I did.", "person_b": "You should double check that link."},
                {"time": "08:35", "person_a": "Something feels off with my account.", "person_b": "Call support right away."},
            ])
        ],
        "transaction": [
            {"title": f"Transaction {i+1}", "content": c} for i, c in enumerate([
                {"time": "08:40", "amount": 75000, "to_account": "XXXX-1187", "status": "Completed"},
                {"time": "07:30", "amount": 500, "to_account": "XXXX-2244", "status": "Completed"},
                {"time": "09:15", "amount": 1200, "to_account": "XXXX-3391", "status": "Completed"},
            ])
        ],
        "document": [
            {"title": "report_final.pdf", "content": {"file_name": "report_final.pdf", "file_type": "PDF", "created": "08:11", "modified": "08:17", "author": "Unknown", "size_kb": 241}},
        ],
        "forensic": [
            {"title": "Forensic Item 1", "content": {"type": "base64", "encoded": "QXR0YWNrIFRpbWU6IDA4OjE2"}},
            {"title": "Forensic Item 2", "content": {"type": "hash", "expected_hash": "ABC123XYZ789", "evidence_hash": "ABC123XYZ789"}},
        ],
    }

    suspects = [
        {"name": "Rahul Mehta", "role": "Former employee", "description": "Worked with victim. Alibi: At home (unverified)."},
        {"name": "Karan Singh", "role": "Friend", "description": "Personal friend of the victim. Alibi: College (verified by classmates)."},
        {"name": "Neha Verma", "role": "Support Executive", "description": "Professional contact via customer support. Alibi: Office (verified by logs)."},
        {"name": "Vikram Shah", "role": "Unknown", "description": "Previous online contact. Alibi: Not verified. Linked to the phishing domain registration pattern."},
    ]

    # Trimmed to 12 questions / 34 pts — two per hinted round (phishing,
    # browser, login) plus one each from chat, suspect, forensic,
    # transaction (x2), and document, so every hint still has a matching
    # question and the case still tells its full story end-to-end.
    questions = [
        {"round_name": "phishing", "question": "Which sender address in the emails is suspicious?",
         "options": ["no-reply@bank-example.test", "newsletter@shopping-example.test", "security-alert@secure-example.test", "support@secure-example.test", "hr@college-example.test", "alerts@secure-example.com", "verify@account-services.test", "billing@bank-example.test"],
         "correct_option": 2, "marks": 3},
        {"round_name": "phishing", "question": "What urgent action did the suspicious email ask the victim to take?",
         "options": ["Update their password", "Download an attachment", "Verify their account immediately", "Confirm a shipping address", "Call customer support", "Claim a prize", "Reset their PIN", "Reply with a screenshot"],
         "correct_option": 2, "marks": 3},
        {"round_name": "browser", "question": "What was the first site visited in the browser history that day?",
         "options": ["mail.example.test", "account-check.example.test", "download.example.test", "news.example.test", "shopping-example.test", "college-example.test", "bank-example.test", "secure-example.test"],
         "correct_option": 3, "marks": 3},
        {"round_name": "browser", "question": "Which site did the victim visit right after opening the phishing email?",
         "options": ["news.example.test", "mail.example.test", "account-check.example.test", "download.example.test", "shopping-example.test", "college-example.test", "bank-example.test", "secure-example.test"],
         "correct_option": 2, "marks": 2},
        {"round_name": "login", "question": "What time was the first successful login after the phishing email was opened?",
         "options": ["07:45", "07:50", "08:31", "08:16", "08:40", "08:45", "09:00", "09:10"],
         "correct_option": 3, "marks": 3},
        {"round_name": "login", "question": "At what time was a failed login attempt recorded?",
         "options": ["07:45", "07:50", "08:14", "08:22", "08:31", "08:40", "08:45", "09:00"],
         "correct_option": 2, "marks": 3},
        {"round_name": "chat", "question": "According to the chat log, what did the victim admit the suspicious email asked for?",
         "options": ["Reset my password", "Confirm my address", "Verify my account", "Update my payment method", "Claim a prize", "Download a file", "Call customer support", "Ignore the email"],
         "correct_option": 2, "marks": 3},
        {"round_name": "suspect", "question": "Which suspect has an unverified alibi and a prior online-contact relationship with the victim?",
         "options": ["Rahul Mehta", "Karan Singh", "Neha Verma", "Aman Gupta", "Vikram Shah", "Deepak Joshi", "Sanjay Kapoor", "Ritu Malhotra"],
         "correct_option": 4, "marks": 3},
        {"round_name": "forensic", "question": "What is the evidence hash recorded in Forensic Item 2 for this case?",
         "options": ["OTP4821HASH", "WIFI5521HASH", "ABC123XYZ789", "XYZ987ABC321", "HASH0816CT", "CT2074HASH", "MISSING75K", "SHA256TEST"],
         "correct_option": 2, "marks": 3},
        {"round_name": "transaction", "question": "What was the amount of the fraudulent transaction?",
         "options": ["₹500", "₹1,200", "₹75,000", "₹3,000", "₹5,000", "₹10,000", "₹25,000", "₹50,000"],
         "correct_option": 2, "marks": 3},
        {"round_name": "transaction", "question": "At what time was the fraudulent transaction completed?",
         "options": ["07:30", "08:40", "09:15", "08:16", "08:22", "08:14", "08:31", "09:00"],
         "correct_option": 1, "marks": 3},
        {"round_name": "document", "question": "Which document was created/modified close to the time of the attack?",
         "options": ["invoice_march.pdf", "report_final.pdf", "photo_backup.zip", "notes.docx", "statement_export.csv", "presentation.pptx", "budget_plan.xlsx", "resume_update.docx"],
         "correct_option": 1, "marks": 2},
    ]

    hints = [
        {"round_name": "phishing", "hint_text": "Compare the sender domain closely — one letter or word often gives away a phishing email.", "penalty": 2},
        {"round_name": "browser", "hint_text": "Cross-reference the browser history timestamps with the phishing email's arrival time.", "penalty": 2},
        {"round_name": "login", "hint_text": "Look for a login that succeeds shortly after the phishing link was likely clicked.", "penalty": 3},
        {"round_name": "chat", "hint_text": "Look closely at what the victim admits doing right after receiving the suspicious email.", "penalty": 2},
        {"round_name": "suspect", "hint_text": "Alibis that are 'not verified' deserve closer scrutiny than verified ones.", "penalty": 3},
        {"round_name": "forensic", "hint_text": "Base64 decodes to readable ASCII text — try the built-in decoder in the Forensic Lab tab.", "penalty": 5},
        {"round_name": "evidence_board", "hint_text": "Think in order: how the attacker got in, what they looked at, how they logged in, then what they did with access.", "penalty": 3},
    ]

    return _seed_case(db, case_kwargs, evidence, suspects, questions, hints)


def seed_in1042(db):
    case_kwargs = dict(
        case_code="IN-1042", title="The OTP That Wasn't",
        description='Priya Nair lost a simulated ₹5,000 after a phone call asking her to "verify KYC" by sharing an '
                     "OTP. A short, beginner-friendly case — fictional data only.",
        victim_name="Priya Nair", financial_loss=5000, duration_minutes=45, active=True,
        correct_suspect="Suresh Kumar",
        correct_attack_method="Vishing call led to OTP disclosure and unauthorized transaction",
        correct_attack_time="14:20",
        correct_evidence_order="email,chat,login,transaction",
    )

    evidence = {
        "email": [
            {"title": "Your KYC is incomplete — Action needed", "content": {"from": "bankcare-support@secure-bank.test", "subject": "Your KYC is incomplete — Action needed", "time": "01:55 PM", "body": "Complete your KYC verification within 1 hour to avoid account suspension. Our support team will call you shortly.", "link": None, "suspicious": True}},
            {"title": "Cultural Fest registrations open", "content": {"from": "newsletter@campus-events.test", "subject": "Cultural Fest registrations open", "time": "11:00 AM", "body": "Register now for the cultural fest.", "link": "https://campus-events.test/register", "suspicious": False}},
            {"title": "Password expiry reminder", "content": {"from": "it-support@college-example.test", "subject": "Password expiry reminder", "time": "10:15 AM", "body": "Your college portal password expires in 5 days. Change it from the portal settings.", "link": "https://college-example.test/settings", "suspicious": False}},
            {"title": "Semester fee due reminder", "content": {"from": "accounts@college-example.test", "subject": "Semester fee due reminder", "time": "09:30 AM", "body": "Your semester fee is due by the end of this week. Pay via the student portal.", "link": "https://college-example.test/fees", "suspicious": False}},
        ],
        "browser": [
            {"title": "Browser Entry 1", "content": {"time": "09:32", "url": "college-example.test/fees"}},
            {"title": "Browser Entry 2", "content": {"time": "14:21", "url": "mybank-example.test/dashboard"}},
        ],
        "chat": [
            {"title": "Call Transcript 1", "content": {"time": "14:12", "person_a": "Hello?", "person_b": "Good afternoon, I'm calling from the bank's KYC verification team."}},
            {"title": "Call Transcript 2", "content": {"time": "14:15", "person_a": "Who is this exactly?", "person_b": "This is Suresh from your bank's KYC department. Your account will be blocked today."}},
            {"title": "Call Transcript 3", "content": {"time": "14:18", "person_a": "What should I do?", "person_b": "Just share the OTP you're receiving right now to verify your identity."}},
            {"title": "Call Transcript 4", "content": {"time": "14:19", "person_a": "Ok, it's 4821.", "person_b": "Thank you, your KYC is now verified."}},
            {"title": "Call Transcript 5", "content": {"time": "14:21", "person_a": "Is that all you need?", "person_b": "Yes, your KYC is complete. Have a nice day."}},
        ],
        "login": [
            {"title": "Login Record 1", "content": {"time": "13:50", "device": "Mobile App", "location": "Chennai", "status": "Success"}},
            {"title": "Login Record 2", "content": {"time": "14:10", "device": "Mobile App", "location": "Chennai", "status": "Success"}},
            {"title": "Login Record 3", "content": {"time": "14:20", "device": "Unknown Device", "location": "Unknown", "status": "Success"}},
            {"title": "Login Record 4", "content": {"time": "14:30", "device": "Mobile App", "location": "Chennai", "status": "Success"}},
        ],
        "transaction": [
            {"title": "Transaction 1", "content": {"time": "13:45", "amount": 200, "to_account": "XXXX-1123", "status": "Completed"}},
            {"title": "Transaction 2", "content": {"time": "14:22", "amount": 5000, "to_account": "XXXX-7734", "status": "Completed"}},
        ],
        "forensic": [
            {"title": "Forensic Item 1", "content": {"type": "base64", "encoded": "QXR0YWNrIFRpbWU6IDE0OjIw"}},
            {"title": "Forensic Item 2", "content": {"type": "hash", "expected_hash": "OTP4821HASH", "evidence_hash": "OTP4821HASH"}},
        ],
    }

    suspects = [
        {"name": "Suresh Kumar", "role": "Caller / Unknown", "description": "Called claiming to be from bank support. Phone number is not linked to any official bank line. Alibi: not verified."},
        {"name": "Ankit Rao", "role": "Classmate", "description": "Studies with the victim. Alibi: In class during the incident (verified by attendance record)."},
    ]

    # Trimmed to 12 questions / 33 pts — the call transcript (chat) is the
    # heart of this case, so it keeps three questions; every other hinted
    # round (phishing, login, suspect, forensic) keeps at least one or two.
    questions = [
        {"round_name": "phishing", "question": "What time was the suspicious KYC email received?",
         "options": ["11:00 AM", "12:30 PM", "01:55 PM", "02:15 PM", "10:45 AM", "03:00 PM", "01:30 PM", "09:00 AM"],
         "correct_option": 2, "marks": 2},
        {"round_name": "phishing", "question": "Who sent the suspicious KYC email?",
         "options": ["accounts@college-example.test", "it-support@college-example.test", "newsletter@campus-events.test", "bankcare-support@secure-bank.test", "kyc@secure-bank.test", "support@secure-bank.in", "alerts@secure-bank.test", "care@secure-bank.test"],
         "correct_option": 3, "marks": 3},
        {"round_name": "chat", "question": "At what time did the call with the scammer begin?",
         "options": ["14:10", "14:12", "14:15", "14:18", "14:19", "14:20", "14:21", "14:22"],
         "correct_option": 1, "marks": 3},
        {"round_name": "chat", "question": "In one word, what sensitive code did the victim share with the caller?",
         "options": ["PIN", "Password", "CVV", "OTP", "Aadhaar number", "Account number", "UPI ID", "Security answer"],
         "correct_option": 3, "marks": 3},
        {"round_name": "chat", "question": "What did the caller say right after receiving the OTP?",
         "options": ["Please hold the line", "Your KYC is now verified", "We will call you back", "Your account is blocked", "Please visit the branch", "Your card is cancelled", "Transaction failed", "Please try again later"],
         "correct_option": 1, "marks": 3},
        {"round_name": "login", "question": "What time was the suspicious login recorded, right after the call?",
         "options": ["14:05", "14:10", "14:15", "14:25", "14:20", "14:30", "13:50", "14:45"],
         "correct_option": 4, "marks": 3},
        {"round_name": "login", "question": "At what time did the victim log back in after noticing the fraud?",
         "options": ["14:10", "14:20", "14:22", "14:25", "14:30", "13:50", "14:35", "14:45"],
         "correct_option": 4, "marks": 2},
        {"round_name": "transaction", "question": "What was the amount of the fraudulent transaction?",
         "options": ["₹500", "₹1,000", "₹2,000", "₹5,000", "₹200", "₹10,000", "₹3,000", "₹7,500"],
         "correct_option": 3, "marks": 3},
        {"round_name": "transaction", "question": "What is the destination account of the fraudulent transaction?",
         "options": ["XXXX-1123", "XXXX-2244", "XXXX-3391", "XXXX-5521", "XXXX-7734", "XXXX-9981", "XXXX-4432", "XXXX-6620"],
         "correct_option": 4, "marks": 3},
        {"round_name": "suspect", "question": "Which suspect is linked to the vishing call with an unverified alibi?",
         "options": ["Ramesh Iyer", "Vivek Choudhary", "Suresh Kumar", "Farhan Sheikh", "Ankit Rao", "Pooja Reddy", "Naveen Bhatia", "Alok Saxena"],
         "correct_option": 2, "marks": 3},
        {"round_name": "suspect", "question": "What is Ankit Rao's alibi status?",
         "options": ["Unverified", "Confirmed by CCTV", "Verified by attendance record", "No alibi given", "Confirmed by a colleague", "Unknown", "Denied involvement", "Not applicable"],
         "correct_option": 2, "marks": 2},
        {"round_name": "forensic", "question": "What does the base64 forensic string decode to?",
         "options": ["Attack Time: 08:16", "Attack Time: 17:05", "Attack Time: 14:20", "Attack Time: 14:22", "Attack Time: 13:50", "Attack Time: 14:12", "Attack Time: 14:30", "Attack Time: 14:10"],
         "correct_option": 2, "marks": 3},
    ]

    hints = [
        {"round_name": "phishing", "hint_text": 'Read the email body carefully — it names exactly what the victim must "complete".', "penalty": 2},
        {"round_name": "login", "hint_text": "Compare login times to the moment the OTP was shared in the call.", "penalty": 2},
        {"round_name": "chat", "hint_text": "A bank never needs you to read out this 4-6 digit code over a call.", "penalty": 2},
        {"round_name": "suspect", "hint_text": "The caller's number was never verified against any real bank line.", "penalty": 2},
        {"round_name": "forensic", "hint_text": "Use the built-in base64 decoder in the Forensic Lab tab.", "penalty": 3},
        {"round_name": "evidence_board", "hint_text": "The attacker needs to reach the victim first, get them talking, then log in, then move the money.", "penalty": 2},
    ]

    return _seed_case(db, case_kwargs, evidence, suspects, questions, hints)


def seed_wf2203(db):
    case_kwargs = dict(
        case_code="WF-2203", title="Free Wi-Fi, Costly Mistake",
        description="Rohan Das lost a simulated ₹3,000 after connecting to a free Wi-Fi hotspot at a mall and "
                     "logging into his wallet app over it. A short, beginner-friendly case — fictional data only.",
        victim_name="Rohan Das", financial_loss=3000, duration_minutes=45, active=True,
        correct_suspect="Manoj Tiwari",
        correct_attack_method="Connected to a rogue public Wi-Fi hotspot, leading to session hijacking and an unauthorized transaction",
        correct_attack_time="17:05",
        correct_evidence_order="browser,login,chat,transaction",
    )

    evidence = {
        "browser": [
            {"title": "Browser Entry 1", "content": {"time": "16:55", "url": "foodcourt-menu.test/mall"}},
            {"title": "Browser Entry 2", "content": {"time": "16:58", "url": "Free_Mall_WiFi_Login.test"}},
            {"title": "Browser Entry 3", "content": {"time": "17:02", "url": "mywallet-app.test/login"}},
            {"title": "Browser Entry 4", "content": {"time": "17:03", "url": "mywallet-app.test/balance"}},
        ],
        "login": [
            {"title": "Login Record 1", "content": {"time": "16:40", "device": "Mobile App", "location": "Home Wifi", "status": "Success"}},
            {"title": "Login Record 2", "content": {"time": "17:00", "device": "Mobile App", "location": "Mall - Connaught Place", "status": "Success"}},
            {"title": "Login Record 3", "content": {"time": "17:05", "device": "Unknown Device", "location": "Unknown", "status": "Success"}},
            {"title": "Login Record 4", "content": {"time": "17:20", "device": "Mobile App", "location": "Mall - Connaught Place", "status": "Success"}},
        ],
        "chat": [
            {"title": "Chat Log 1", "content": {"time": "17:10", "person_a": "My wallet app logged me out suddenly.", "person_b": "Did you use the mall's free wifi?"}},
            {"title": "Chat Log 2", "content": {"time": "17:11", "person_a": "Yes, I connected a few minutes back.", "person_b": "That wifi isn't official! Change your password now."}},
            {"title": "Chat Log 3", "content": {"time": "17:12", "person_a": "I already changed it, but ₹3,000 is missing!", "person_b": "Contact your bank immediately and report it."}},
            {"title": "Chat Log 4", "content": {"time": "17:15", "person_a": "Done, they've blocked the card for now.", "person_b": "Good, also avoid that wifi again."}},
        ],
        "transaction": [
            {"title": "Transaction 1", "content": {"time": "16:50", "amount": 150, "to_account": "XXXX-2210", "status": "Completed"}},
            {"title": "Transaction 2", "content": {"time": "17:06", "amount": 3000, "to_account": "XXXX-5521", "status": "Completed"}},
        ],
        "forensic": [
            {"title": "Forensic Item 1", "content": {"type": "base64", "encoded": "QXR0YWNrIFRpbWU6IDE3OjA1"}},
            {"title": "Forensic Item 2", "content": {"type": "hash", "expected_hash": "WIFI5521HASH", "evidence_hash": "WIFI5521HASH"}},
        ],
    }

    suspects = [
        {"name": "Manoj Tiwari", "role": "Mall Wi-Fi Kiosk Vendor", "description": "Runs a small Wi-Fi kiosk near the food court. Alibi: not verified. The same hotspot name has been flagged in two other complaints."},
        {"name": "Ritika Sharma", "role": "Friend", "description": "Was with the victim at the mall. Alibi: confirmed by CCTV footage."},
    ]

    # Trimmed to 11 questions / 33 pts, all worth 3 — login gets an extra
    # question since the session-hijack is the crux of this case.
    questions = [
        {"round_name": "browser", "question": "What suspicious Wi-Fi network did the victim connect to?",
         "options": ["Mall_Guest_Wifi", "CP_Free_Internet", "Free_Mall_WiFi_Login.test", "Public_Hotspot_247", "Cafe_Free_Net", "Shopping_Complex_Wifi", "Open_Network_5G", "Guest_Portal_Wifi"],
         "correct_option": 2, "marks": 3},
        {"round_name": "browser", "question": "At what time did the victim log into the wallet app over this Wi-Fi?",
         "options": ["16:58", "17:00", "17:02", "17:05", "17:06", "17:10", "17:11", "17:15"],
         "correct_option": 2, "marks": 3},
        {"round_name": "login", "question": "What time was the hijacked/unknown login recorded?",
         "options": ["16:40", "16:58", "17:00", "17:02", "17:06", "17:05", "17:11", "17:20"],
         "correct_option": 5, "marks": 3},
        {"round_name": "login", "question": "What device recorded the hijacked login?",
         "options": ["Mobile App", "Chrome/Windows", "Unknown Device", "Tablet", "Firefox/Mac", "Safari/iOS", "Edge/Windows", "Linux Terminal"],
         "correct_option": 2, "marks": 3},
        {"round_name": "login", "question": "Where was the victim's own 17:00 login recorded from?",
         "options": ["Home Wifi", "Unknown", "Mall - Connaught Place", "Chennai", "Delhi", "Mumbai", "Bengaluru", "Pune"],
         "correct_option": 2, "marks": 3},
        {"round_name": "chat", "question": "In one/two words, what did the friend blame for the issue?",
         "options": ["Weak password", "Phishing email", "SIM swap", "Free wifi", "Malware app", "Public charging port", "Fake QR code", "Old software"],
         "correct_option": 3, "marks": 3},
        {"round_name": "chat", "question": "What did the friend suggest after the money went missing?",
         "options": ["Wait and watch", "Change the Wi-Fi password", "Contact your bank immediately", "Reinstall the wallet app", "Ignore small amounts", "File a police report first", "Block the friend's number", "Visit the mall office"],
         "correct_option": 2, "marks": 3},
        {"round_name": "transaction", "question": "What amount was fraudulently transferred?",
         "options": ["₹500", "₹1,000", "₹2,000", "₹3,000", "₹150", "₹5,000", "₹10,000", "₹7,500"],
         "correct_option": 3, "marks": 3},
        {"round_name": "transaction", "question": "At what time was the fraudulent transaction completed?",
         "options": ["16:50", "17:00", "17:02", "17:05", "17:06", "17:10", "17:11", "17:20"],
         "correct_option": 4, "marks": 3},
        {"round_name": "suspect", "question": "Which suspect runs the flagged Wi-Fi hotspot with an unverified alibi?",
         "options": ["Devendra Rao", "Kunal Mehra", "Manoj Tiwari", "Sameer Khan", "Ritika Sharma", "Arjun Nair", "Priyanka Das", "Rajiv Menon"],
         "correct_option": 2, "marks": 3},
        {"round_name": "forensic", "question": "What does the base64 forensic string decode to?",
         "options": ["Attack Time: 08:16", "Attack Time: 14:20", "Attack Time: 17:00", "Attack Time: 17:05", "Attack Time: 17:06", "Attack Time: 16:58", "Attack Time: 17:11", "Attack Time: 17:20"],
         "correct_option": 3, "marks": 3},
    ]

    hints = [
        {"round_name": "browser", "hint_text": 'Public Wi-Fi names ending in oddly specific ".test"-style domains are worth a second look.', "penalty": 2},
        {"round_name": "login", "hint_text": "Compare login times right after the wallet-app browser visit.", "penalty": 2},
        {"round_name": "chat", "hint_text": "The friend's second message names the exact thing to blame.", "penalty": 2},
        {"round_name": "suspect", "hint_text": "One suspect has an alibi confirmed by CCTV — the other does not.", "penalty": 2},
        {"round_name": "forensic", "hint_text": "Use the built-in base64 decoder in the Forensic Lab tab.", "penalty": 3},
        {"round_name": "evidence_board", "hint_text": "Think: connect to Wi-Fi first, then the hijacked login happens, then the victim notices and chats about it, then the money moves.", "penalty": 2},
    ]

    return _seed_case(db, case_kwargs, evidence, suspects, questions, hints)


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_admin(db)
        c1 = seed_ct2074(db)
        c2 = seed_in1042(db)
        c3 = seed_wf2203(db)
        print("\n[seed] Done. Log in as admin and create teams from the Admin Dashboard.")
    finally:
        db.close()


if __name__ == "__main__":
    main()