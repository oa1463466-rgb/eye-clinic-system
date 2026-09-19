from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from pathlib import Path
from datetime import datetime

APP_DIR = Path(__file__).resolve().parent
DB = APP_DIR / "clinic.db"

app = Flask(__name__)
app.secret_key = "CHANGE-THIS-SECRET-KEY"

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_no TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        gender TEXT,
        birth_date TEXT,
        phone TEXT,
        national_id TEXT,
        address TEXT,
        occupation TEXT,
        notes TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        visit_date TEXT NOT NULL,
        chief_complaint TEXT,
        history TEXT,
        va_od TEXT,
        va_os TEXT,
        iop_od TEXT,
        iop_os TEXT,
        sph_od TEXT,
        cyl_od TEXT,
        axis_od TEXT,
        add_od TEXT,
        sph_os TEXT,
        cyl_os TEXT,
        axis_os TEXT,
        add_os TEXT,
        slit_lamp_od TEXT,
        slit_lamp_os TEXT,
        fundus_od TEXT,
        fundus_os TEXT,
        diagnosis TEXT,
        treatment TEXT,
        follow_up TEXT,
        FOREIGN KEY(patient_id) REFERENCES patients(id)
    );

    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        appointment_date TEXT NOT NULL,
        appointment_time TEXT NOT NULL,
        reason TEXT,
        status TEXT DEFAULT 'مجدول',
        FOREIGN KEY(patient_id) REFERENCES patients(id)
    );
    """)
    conn.commit()
    conn.close()

def next_file_no():
    conn = get_db()
    row = conn.execute("SELECT id FROM patients ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    n = (row["id"] + 1) if row else 1
    return f"OPH-{n:06d}"

@app.context_processor
def inject_globals():
    return {"now": datetime.now().strftime("%Y-%m-%d %H:%M")}

@app.route("/", methods=["GET"])
def index():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    conn = get_db()
    patients = conn.execute("SELECT COUNT(*) c FROM patients").fetchone()["c"]
    visits_today = conn.execute(
        "SELECT COUNT(*) c FROM visits WHERE date(visit_date)=date('now','localtime')"
    ).fetchone()["c"]
    appointments = conn.execute(
        "SELECT COUNT(*) c FROM appointments WHERE appointment_date=date('now','localtime')"
    ).fetchone()["c"]
    recent = conn.execute("""
        SELECT p.*, 
        (SELECT MAX(v.visit_date) FROM visits v WHERE v.patient_id=p.id) last_visit
        FROM patients p ORDER BY p.id DESC LIMIT 8
    """).fetchall()
    conn.close()
    return render_template("dashboard.html", patients=patients, visits_today=visits_today,
                           appointments=appointments, recent=recent)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        if username == "admin" and password == "admin123":
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("index"))
        flash("اسم المستخدم أو كلمة المرور غير صحيحة", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/patients")
def patients():
    if not session.get("logged_in"): return redirect(url_for("login"))
    q = request.args.get("q","").strip()
    conn = get_db()
    if q:
        rows = conn.execute("""
            SELECT * FROM patients
            WHERE full_name LIKE ? OR file_no LIKE ? OR phone LIKE ? OR national_id LIKE ?
            ORDER BY id DESC
        """, (f"%{q}%",f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
    else:
        rows = conn.execute("SELECT * FROM patients ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("patients.html", patients=rows, q=q)

@app.route("/patients/new", methods=["GET","POST"])
def new_patient():
    if not session.get("logged_in"): return redirect(url_for("login"))
    if request.method == "POST":
        data = {k: request.form.get(k,"").strip() for k in
                ["full_name","gender","birth_date","phone","national_id","address","occupation","notes"]}
        if not data["full_name"]:
            flash("اسم المريض مطلوب", "danger")
            return render_template("patient_form.html", patient=None, file_no=next_file_no())
        file_no = next_file_no()
        conn = get_db()
        try:
            cur = conn.execute("""
                INSERT INTO patients
                (file_no,full_name,gender,birth_date,phone,national_id,address,occupation,notes,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (file_no, data["full_name"],data["gender"],data["birth_date"],data["phone"],
                  data["national_id"],data["address"],data["occupation"],data["notes"],
                  datetime.now().isoformat(timespec="minutes")))
            conn.commit()
            pid = cur.lastrowid
        except sqlite3.IntegrityError:
            conn.rollback()
            flash("تعذر حفظ المريض، حاول مرة أخرى", "danger")
            return render_template("patient_form.html", patient=None, file_no=file_no)
        finally:
            conn.close()
        return redirect(url_for("patient_detail", patient_id=pid))
    return render_template("patient_form.html", patient=None, file_no=next_file_no())

@app.route("/patients/<int:patient_id>")
def patient_detail(patient_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    conn = get_db()
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    visits = conn.execute("SELECT * FROM visits WHERE patient_id=? ORDER BY visit_date DESC", (patient_id,)).fetchall()
    appointments = conn.execute("SELECT * FROM appointments WHERE patient_id=? ORDER BY appointment_date DESC, appointment_time DESC", (patient_id,)).fetchall()
    conn.close()
    if not patient:
        flash("المريض غير موجود", "danger")
        return redirect(url_for("patients"))
    return render_template("patient_detail.html", patient=patient, visits=visits, appointments=appointments)

@app.route("/patients/<int:patient_id>/visit/new", methods=["GET","POST"])
def new_visit(patient_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    conn = get_db()
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    conn.close()
    if not patient: return redirect(url_for("patients"))
    if request.method == "POST":
        fields = ["chief_complaint","history","va_od","va_os","iop_od","iop_os",
                  "sph_od","cyl_od","axis_od","add_od","sph_os","cyl_os","axis_os","add_os",
                  "slit_lamp_od","slit_lamp_os","fundus_od","fundus_os","diagnosis","treatment","follow_up"]
        vals = [request.form.get(f,"").strip() for f in fields]
        conn = get_db()
        conn.execute(f"""
            INSERT INTO visits
            (patient_id,visit_date,{",".join(fields)})
            VALUES (?,datetime('now','localtime'),{",".join(["?"]*len(fields))})
        """, [patient_id] + vals)
        conn.commit(); conn.close()
        flash("تم حفظ الزيارة والفحص بنجاح", "success")
        return redirect(url_for("patient_detail", patient_id=patient_id))
    return render_template("visit_form.html", patient=patient)

@app.route("/appointments/new/<int:patient_id>", methods=["GET","POST"])
def new_appointment(patient_id):
    if not session.get("logged_in"): return redirect(url_for("login"))
    conn = get_db()
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    conn.close()
    if request.method == "POST":
        conn = get_db()
        conn.execute("""INSERT INTO appointments(patient_id,appointment_date,appointment_time,reason,status)
                        VALUES(?,?,?,?,?)""",
                     (patient_id,request.form["appointment_date"],request.form["appointment_time"],
                      request.form.get("reason",""),"مجدول"))
        conn.commit(); conn.close()
        flash("تم حجز الموعد", "success")
        return redirect(url_for("patient_detail", patient_id=patient_id))
    return render_template("appointment_form.html", patient=patient)

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
