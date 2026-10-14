from flask import Flask, request, jsonify, session, render_template, redirect, url_for, flash
from datetime import datetime
import math
from flask_cors import CORS
import os
import pymysql
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv("SECRET_KEY")

if not app.secret_key:
    raise RuntimeError("SECRET_KEY environment variable is required")

# اتصال به دیتابیس MySQL
import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

app.secret_key = os.getenv("SECRET_KEY")

if not app.secret_key:
    raise RuntimeError("SECRET_KEY environment variable is required")


def get_db_connection():
    connection = pymysql.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", "3306")),
        charset="utf8mb4",
        ssl={"ca": os.path.join(os.path.dirname(os.path.abspath(__file__)), "ca.pem")},
        connect_timeout=15
    )
    return connection

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/login-page")
def login_page():
    return render_template("index.html")


@app.route("/test-db")
def test_db():
    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute(
        "SELECT User_ID, Username, Role, Status FROM users"
    )

    users = cursor.fetchall()

    cursor.close()
    connection.close()

    return str(users)

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    username = data.get("username")
    password = data.get("password")

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT User_ID, Username, Password, Role, Status
        FROM users
        WHERE Username = %s
        """,
        (username,)
    )

    user = cursor.fetchone()

    cursor.close()
    connection.close()

    if user is None:
        return jsonify({
            "success": False,
            "message": "Username or password is incorrect"
        }), 401

    stored_password = user[2]

    try:
        password_matches = check_password_hash(
            stored_password, password
        )
    except (ValueError, TypeError):
        # Support existing plain-text passwords
        password_matches = stored_password == password

    if not password_matches:
        return jsonify({
            "success": False,
            "message": "Username or password is incorrect"
        }), 401

    if user[4] != "Active":
        return jsonify({
            "success": False,
            "message": "User account is not active"
        }), 403
        
    # Update last login date and time
    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE users
            SET Last_Login = NOW()
            WHERE User_ID = %s
        """, (user[0],))
        connection.commit()

    except Exception:
        connection.rollback()
        app.logger.exception("Failed to update last login time")

    finally:
        cursor.close()
        connection.close()

    session["user_id"] = user[0]
    session["username"] = user[1]
    session["role"] = user[3]

    return jsonify({
        "success": True,
        "message": "Login successful",
        "user_id": user[0],
        "username": user[1],
        "role": user[3]
    })
    
@app.route("/settings/change-password", methods=["POST"])
def change_password():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "Please login first."
        }), 401

    data = request.get_json(silent=True) or {}

    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    confirm_password = data.get("confirm_password", "")

    if not all([
        current_password,
        new_password,
        confirm_password
    ]):
        return jsonify({
            "success": False,
            "message": "Please fill in all fields."
        }), 400

    if len(new_password) < 8:
        return jsonify({
            "success": False,
            "message": "New password must be at least 8 characters."
        }), 400

    if new_password != confirm_password:
        return jsonify({
            "success": False,
            "message": "New passwords do not match."
        }), 400

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT Password
            FROM users
            WHERE User_ID = %s AND Status = 'Active'
            """,
            (session["user_id"],)
        )

        user = cursor.fetchone()


        if user is None:
            return jsonify({
                "success": False,
                "message": "Active user account not found."
            }), 404

        stored_password = user[0]

        if stored_password.startswith(("pbkdf2:", "scrypt:")):
            password_matches = check_password_hash(
                stored_password, current_password
            )
        else:
            password_matches = stored_password == current_password

        if not password_matches:
            return jsonify({
                "success": False,
                "message": "Current password is incorrect."
            }), 400

        if current_password == new_password:
            return jsonify({
                "success": False,
                "message": "Choose a different new password."
            }), 400

        hashed_password = generate_password_hash(new_password)

        cursor.execute(
            """
            UPDATE users
            SET Password = %s
            WHERE User_ID = %s
            """,
            (hashed_password, session["user_id"])
        )

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Password changed successfully."
        })

    except Exception:
        connection.rollback()
        app.logger.exception("Password change failed")

        return jsonify({
            "success": False,
            "message": "Unable to change password. Please try again."
        }), 500

    finally:
        cursor.close()
        connection.close()
    
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM students")

    total_students = cursor.fetchone()[0]
    
    cursor.execute("""
    SELECT COUNT(*)
    FROM students
    WHERE Status = 'Active'
""")

    active_students = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM rooms")
    total_rooms = cursor.fetchone()[0]
    
    cursor.execute("""
    SELECT COUNT(*)
    FROM beds
    WHERE Status = 'Available'
""")
    available_beds = cursor.fetchone()[0]
    
    cursor.execute("""
    SELECT
        SUM(CASE WHEN Room_Status = 'Full' THEN 1 ELSE 0 END),
        SUM(CASE WHEN Room_Status = 'Half' THEN 1 ELSE 0 END),
        SUM(CASE WHEN Room_Status = 'Empty' THEN 1 ELSE 0 END),
        SUM(CASE WHEN Room_Status = 'Repair' THEN 1 ELSE 0 END)
    FROM (
        SELECT
            r.Room_ID,
            CASE
                WHEN r.Status = 'Repair' THEN 'Repair'
                WHEN SUM(CASE WHEN b.Status = 'Occupied' THEN 1 ELSE 0 END) = COUNT(b.Bed_ID)
                     AND COUNT(b.Bed_ID) > 0 THEN 'Full'
                WHEN SUM(CASE WHEN b.Status = 'Occupied' THEN 1 ELSE 0 END) > 0 THEN 'Half'
                ELSE 'Empty'
            END AS Room_Status
        FROM rooms r
        LEFT JOIN beds b
            ON r.Room_ID = b.Room_ID
        GROUP BY r.Room_ID, r.Status
    ) AS room_statuses
""")

    room_full, room_half, room_empty, room_repair = cursor.fetchone()
    
    # Monthly Payments
    cursor.execute("""
    SELECT COALESCE(SUM(Amount), 0)
    FROM payments
    WHERE MONTH(Payment_Date) = MONTH(CURDATE())
      AND YEAR(Payment_Date) = YEAR(CURDATE())
""")

    monthly_payments = cursor.fetchone()[0]
    
    # Payment History
    cursor.execute("""
    SELECT
        Payment_Month,
        SUM(Amount) AS Total_Amount
    FROM payments
    WHERE Status = 'Paid'
    GROUP BY Payment_Month
    ORDER BY MIN(Payment_Date) DESC
""")

    payment_history = cursor.fetchall()
    
    # Occupancy Overview
    cursor.execute("""
    SELECT
        COUNT(*) AS total_beds,
        SUM(CASE WHEN Status = 'Occupied' THEN 1 ELSE 0 END) AS occupied_beds,
        SUM(CASE WHEN Status = 'Available' THEN 1 ELSE 0 END) AS available_beds
    FROM beds
""")

    total_beds, occupied_beds, available_beds = cursor.fetchone()

    occupancy_rate = round((occupied_beds / total_beds) * 100, 2) if total_beds > 0 else 0

    cursor.close()
    connection.close()

    return render_template(
        "dashboard.html",
        username=session["username"],
        role=session["role"],
        total_students=total_students,
        active_students=active_students,
        total_rooms=total_rooms,
        available_beds=available_beds,
        room_full=room_full,
        room_half=room_half,
        room_empty=room_empty,
        room_repair=room_repair,
        monthly_payments=monthly_payments,
        payment_history=payment_history,
        total_beds=total_beds,
        occupied_beds=occupied_beds,
        occupancy_rate=occupancy_rate
        
        
    )
    
@app.route('/occupancy')
def occupancy():
    
    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) AS total_beds,
            SUM(CASE WHEN Status = 'Occupied' THEN 1 ELSE 0 END) AS occupied_beds,
            SUM(CASE WHEN Status = 'Available' THEN 1 ELSE 0 END) AS available_beds
        FROM beds
    """)

    total_beds, occupied_beds, available_beds = cursor.fetchone()

    occupancy_rate = round(
        (occupied_beds / total_beds) * 100, 2
    ) if total_beds > 0 else 0

    cursor.close()
    connection.close()

    return render_template(
        'occupancy.html',
        total_beds=total_beds,
        occupied_beds=occupied_beds,
        available_beds=available_beds,
        occupancy_rate=occupancy_rate
    )
    
@app.route('/room-status')
def room_status():
    
    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            r.Room_ID,
            r.Room_Number,
            r.Status AS Room_Status,
            COUNT(b.Bed_ID) AS Total_Beds,
            SUM(
                CASE
                    WHEN b.Status = 'Occupied' THEN 1
                    ELSE 0
                END
            ) AS Occupied_Beds,
            SUM(
                CASE
                    WHEN b.Status = 'Available' THEN 1
                    ELSE 0
                END
            ) AS Available_Beds
        FROM rooms r
        LEFT JOIN beds b
            ON r.Room_ID = b.Room_ID
        GROUP BY
            r.Room_ID,
            r.Room_Number,
            r.Status
        ORDER BY r.Room_ID
    """)

    rooms = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'room_status.html',
        rooms=rooms
    )
    
@app.route('/payment-history')
def payment_history_page():
    
    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            p.Payment_ID,
            s.Student_ID,
            s.First_Name,
            s.Last_Name,
            p.Amount,
            p.Payment_Month,
            p.Payment_Date,
            p.Receipt_Number,
            p.Status
        FROM payments p
        JOIN students s
            ON p.Student_ID = s.Student_ID
        ORDER BY p.Payment_Date DESC
    """)

    payments = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'payment_history.html',
        payments=payments
    )
    
@app.route('/students/add', methods=['GET', 'POST'])
def add_student():

    if "user_id" not in session:
        return "Please login first", 401

    if request.method == 'POST':

        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        father_name = request.form.get('father_name')
        phone = request.form.get('phone')
        id_number = request.form.get('id_number')
        education_type = request.form.get('education_type')
        university_school = request.form.get('university_school')
        department = request.form.get('department')
        semester_grade = request.form.get('semester_grade')
        entry_date = request.form.get('entry_date')
        status = request.form.get('status')

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO students
            (
                First_Name,
                Last_Name,
                Father_Name,
                Phone,
                ID_Number,
                Education_Type,
                University_School,
                Department,
                Semester_Grade,
                Entry_Date,
                Status
            )
            VALUES
            (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
        """, (
            first_name,
            last_name,
            father_name,
            phone,
            id_number,
            education_type,
            university_school,
            department,
            semester_grade,
            entry_date,
            status
        ))

        connection.commit()

        cursor.close()
        connection.close()

        return redirect('/students')

    return render_template("add_student.html")

@app.route('/students/<int:student_id>')
def student_details(student_id):

    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            Student_ID,
            First_Name,
            Last_Name,
            Father_Name,
            Phone,
            ID_Number,
            Education_Type,
            University_School,
            Department,
            Semester_Grade,
            Entry_Date,
            Status
        FROM students
        WHERE Student_ID = %s
    """, (student_id,))

    student = cursor.fetchone()
    
    # Room and Bed Information
    cursor.execute("""
        SELECT
            r.Room_Number,
            b.Bed_ID,
            b.Bed_Number,
            ra.Start_Date,
            ra.End_Date,
            ra.Status
        FROM room_assignments ra
        JOIN beds b
            ON ra.Bed_ID = b.Bed_ID
        JOIN rooms r
            ON b.Room_ID = r.Room_ID
        WHERE ra.Student_ID = %s
        AND ra.Status = 'Active'
        LIMIT 1
    """, (student_id,))

    room_info = cursor.fetchone()
    
    # Room Capacity Information
    room_capacity = None

    if room_info:

        cursor.execute("""
            SELECT
            COUNT(*) AS total_beds,
            SUM(CASE WHEN Status = 'Occupied' THEN 1 ELSE 0 END) AS occupied_beds,
            SUM(CASE WHEN Status = 'Available' THEN 1 ELSE 0 END) AS available_beds
        FROM beds
        WHERE Room_ID = (
            SELECT Room_ID
            FROM beds
            WHERE Bed_ID = %s
        )
    """, (room_info[1],))

    room_capacity = cursor.fetchone()
    
    # Payment Information
    cursor.execute("""
        SELECT
            Amount,
            Payment_Month,
            Payment_Date,
            Receipt_Number,
            Status
        FROM payments
        WHERE Student_ID = %s
        ORDER BY Payment_Date DESC
    """, (student_id,))

    payments = cursor.fetchall()
    
    # Payment Summary
    cursor.execute("""
        SELECT
            COALESCE(SUM(Amount), 0),
            MAX(Payment_Date)
        FROM payments
        WHERE Student_ID = %s
        AND Status = 'Paid'
    """, (student_id,))

    total_paid, last_payment = cursor.fetchone()
    
    # Current Month Payment Status
    cursor.execute("""
        SELECT COUNT(*)
        FROM payments
        WHERE Student_ID = %s
        AND Status = 'Paid'
        AND MONTH(Payment_Date) = MONTH(CURDATE())
        AND YEAR(Payment_Date) = YEAR(CURDATE())
    """, (student_id,))

    current_month_payment = cursor.fetchone()[0]

    if current_month_payment > 0:
        payment_status = "Paid"
    else:
        payment_status = "Unpaid"

    cursor.close()
    connection.close()

    if student is None:
        return "Student not found", 404

    return render_template(
        "student_details.html",
        student=student,
        room_info=room_info,
        room_capacity=room_capacity,
        payments=payments,
        total_paid=total_paid,
        last_payment=last_payment,
        payment_status=payment_status
        
    )
    
@app.route('/students/<int:student_id>/assign', methods=['GET', 'POST'])
def assign_student(student_id):

    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    # Get student
    cursor.execute("""
        SELECT
            Student_ID,
            First_Name,
            Last_Name
        FROM students
        WHERE Student_ID = %s
    """, (student_id,))

    student = cursor.fetchone()

    if student is None:
        cursor.close()
        connection.close()
        return "Student not found", 404

    # Check existing active assignment
    cursor.execute("""
        SELECT Assignment_ID
        FROM room_assignments
        WHERE Student_ID = %s
          AND Status = 'Active'
        LIMIT 1
    """, (student_id,))

    existing_assignment = cursor.fetchone()

    if existing_assignment:
        cursor.close()
        connection.close()

        return "This student is already assigned to a bed.", 400

    # =========================
    # POST - Assign Bed
    # =========================

    if request.method == 'POST':

        bed_id = request.form.get('bed_id', type=int)
        start_date = request.form.get('start_date')

        if not bed_id or not start_date:
            cursor.close()
            connection.close()

            return "Bed and start date are required.", 400

        # Check that selected bed is still available
        cursor.execute("""
            SELECT Bed_ID
            FROM beds
            WHERE Bed_ID = %s
              AND Status = 'Available'
        """, (bed_id,))

        available_bed = cursor.fetchone()

        if available_bed is None:
            cursor.close()
            connection.close()

            return "This bed is no longer available.", 400

        # Create assignment
        cursor.execute("""
            INSERT INTO room_assignments
            (
                Student_ID,
                Bed_ID,
                Start_Date,
                End_Date,
                Status
            )
            VALUES
            (
                %s, %s, %s, NULL, 'Active'
            )
        """, (
            student_id,
            bed_id,
            start_date
        ))

        # Change bed status
        cursor.execute("""
            UPDATE beds
            SET Status = 'Occupied'
            WHERE Bed_ID = %s
        """, (bed_id,))

        connection.commit()

        cursor.close()
        connection.close()

        return redirect(f'/students/{student_id}')

    # =========================
    # GET - Available Beds
    # =========================

    cursor.execute("""
        SELECT
            b.Bed_ID,
            b.Bed_Number,
            r.Room_ID,
            r.Room_Number
        FROM beds b
        JOIN rooms r
            ON b.Room_ID = r.Room_ID
        WHERE b.Status = 'Available'
        ORDER BY r.Room_ID, b.Bed_ID
    """)

    available_beds = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "assign_student.html",
        student=student,
        available_beds=available_beds
    )
    
@app.route('/payments/add', methods=['GET', 'POST'])
def add_payment():

    if "user_id" not in session:
        return "Please login first", 401

    student_id = request.args.get('student_id', type=int)

    if not student_id:
        return "Student ID is required", 400

    connection = get_db_connection()
    cursor = connection.cursor()

    # Get student
    cursor.execute("""
        SELECT
            Student_ID,
            First_Name,
            Last_Name
        FROM students
        WHERE Student_ID = %s
    """, (student_id,))

    student = cursor.fetchone()

    if student is None:
        cursor.close()
        connection.close()
        return "Student not found", 404

    # =========================
    # POST - Save Payment
    # =========================

    if request.method == 'POST':

        amount = request.form.get('amount')
        payment_month = request.form.get('payment_month')
        payment_date = request.form.get('payment_date')
        receipt_number = request.form.get('receipt_number')
        status = request.form.get('status')

        # Check duplicate paid payment
        cursor.execute("""
            SELECT Payment_ID
            FROM payments
            WHERE Student_ID = %s
              AND Payment_Month = %s
              AND Status = 'Paid'
            LIMIT 1
        """, (student_id, payment_month))

        existing_payment = cursor.fetchone()

        if existing_payment:

            # Generate next receipt for displaying the form again
            cursor.execute("""
                SELECT Receipt_Number
                FROM payments
                WHERE Receipt_Number IS NOT NULL
                ORDER BY Payment_ID DESC
                LIMIT 1
            """)

            last_receipt = cursor.fetchone()

            next_receipt = "REC-2026-001"

            if last_receipt and last_receipt[0]:

                try:
                    last_number = int(
                        last_receipt[0].split("-")[-1]
                    )

                    next_receipt = (
                        f"REC-{datetime.now().year}-{last_number + 1:03d}"
                    )

                except:
                    pass

            cursor.close()
            connection.close()

            return render_template(
                "add_payment.html",
                student=student,
                next_receipt=next_receipt,
                error="Payment for this month has already been recorded."
            ), 400

        # Save payment
        cursor.execute("""
            INSERT INTO payments
            (
                Student_ID,
                Amount,
                Payment_Month,
                Payment_Date,
                Receipt_Number,
                Status
            )
            VALUES
            (
                %s, %s, %s, %s, %s, %s
            )
        """, (
            student_id,
            amount,
            payment_month,
            payment_date,
            receipt_number,
            status
        ))

        connection.commit()

        cursor.close()
        connection.close()

        return redirect(f'/students/{student_id}')

    # =========================
    # GET - Show Payment Form
    # =========================

    cursor.execute("""
        SELECT Receipt_Number
        FROM payments
        WHERE Receipt_Number IS NOT NULL
        ORDER BY Payment_ID DESC
        LIMIT 1
    """)

    last_receipt = cursor.fetchone()

    next_receipt = "REC-2026-001"

    if last_receipt and last_receipt[0]:

        try:
            last_number = int(
                last_receipt[0].split("-")[-1]
            )

            next_receipt = (
                f"REC-{datetime.now().year}-{last_number + 1:03d}"
            )

        except:
            pass

    cursor.close()
    connection.close()

    return render_template(
        "add_payment.html",
        student=student,
        next_receipt=next_receipt
    )
    
@app.route('/students/<int:student_id>/edit', methods=['GET', 'POST'])
def edit_student(student_id):

    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':

        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        father_name = request.form.get('father_name')
        phone = request.form.get('phone')
        id_number = request.form.get('id_number')
        education_type = request.form.get('education_type')
        university_school = request.form.get('university_school')
        department = request.form.get('department')
        semester_grade = request.form.get('semester_grade')
        entry_date = request.form.get('entry_date')
        status = request.form.get('status')

        cursor.execute("""
            UPDATE students
            SET
                First_Name = %s,
                Last_Name = %s,
                Father_Name = %s,
                Phone = %s,
                ID_Number = %s,
                Education_Type = %s,
                University_School = %s,
                Department = %s,
                Semester_Grade = %s,
                Entry_Date = %s,
                Status = %s
            WHERE Student_ID = %s
        """, (
            first_name,
            last_name,
            father_name,
            phone,
            id_number,
            education_type,
            university_school,
            department,
            semester_grade,
            entry_date,
            status,
            student_id
        ))

        connection.commit()

        cursor.close()
        connection.close()

        return redirect(f'/students/{student_id}')

    cursor.execute("""
        SELECT
            Student_ID,
            First_Name,
            Last_Name,
            Father_Name,
            Phone,
            ID_Number,
            Education_Type,
            University_School,
            Department,
            Semester_Grade,
            Entry_Date,
            Status
        FROM students
        WHERE Student_ID = %s
    """, (student_id,))

    student = cursor.fetchone()

    cursor.close()
    connection.close()

    if student is None:
        return "Student not found", 404

    return render_template(
        "edit_student.html",
        student=student
    )
    
@app.route('/students/<int:student_id>/delete', methods=['POST'])
def delete_student(student_id):

    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT Student_ID
        FROM students
        WHERE Student_ID = %s
    """, (student_id,))

    student = cursor.fetchone()

    if student is None:

        cursor.close()
        connection.close()

        return "Student not found", 404

    cursor.execute("""
        DELETE FROM students
        WHERE Student_ID = %s
    """, (student_id,))

    connection.commit()

    cursor.close()
    connection.close()

    return redirect('/students')
    
@app.route('/students')
def students_page():

    if "user_id" not in session:
        return "Please login first", 401

    search = request.args.get('search', '').strip()

    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    connection = get_db_connection()
    cursor = connection.cursor()

    # Count students
    if search:

        search_value = f"%{search}%"

        cursor.execute("""
            SELECT COUNT(*)
            FROM students
            WHERE
                First_Name LIKE %s
                OR Last_Name LIKE %s
                OR Phone LIKE %s
                OR ID_Number LIKE %s
                OR University_School LIKE %s
                OR Department LIKE %s
        """, (
            search_value,
            search_value,
            search_value,
            search_value,
            search_value,
            search_value
        ))

    else:

        cursor.execute("""
            SELECT COUNT(*)
            FROM students
        """)

    total_students = cursor.fetchone()[0]

    total_pages = math.ceil(total_students / per_page)

    # Get students
    if search:

        search_value = f"%{search}%"

        cursor.execute("""
            SELECT
                Student_ID,
                First_Name,
                Last_Name,
                University_School,
                Department,
                Status
            FROM students
            WHERE
                First_Name LIKE %s
                OR Last_Name LIKE %s
                OR Phone LIKE %s
                OR ID_Number LIKE %s
                OR University_School LIKE %s
                OR Department LIKE %s
            ORDER BY Student_ID DESC
            LIMIT %s OFFSET %s
        """, (
            search_value,
            search_value,
            search_value,
            search_value,
            search_value,
            search_value,
            per_page,
            offset
        ))

    else:

        cursor.execute("""
            SELECT
                Student_ID,
                First_Name,
                Last_Name,
                University_School,
                Department,
                Status
            FROM students
            ORDER BY Student_ID DESC
            LIMIT %s OFFSET %s
        """, (
            per_page,
            offset
        ))

    students = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "students.html",
        students=students,
        search=search,
        page=page,
        total_pages=total_pages,
        total_students=total_students
    )

@app.route('/rooms')
def rooms_page():

    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            r.Room_ID,
            r.Room_Number,
            r.Status,
            COUNT(b.Bed_ID) AS Total_Beds,
            SUM(CASE WHEN b.Status = 'Occupied' THEN 1 ELSE 0 END) AS Occupied_Beds,
            SUM(CASE WHEN b.Status = 'Available' THEN 1 ELSE 0 END) AS Available_Beds
        FROM rooms r
        LEFT JOIN beds b
            ON r.Room_ID = b.Room_ID
        GROUP BY
            r.Room_ID,
            r.Room_Number,
            r.Status
        ORDER BY r.Room_ID
    """)

    rooms = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'rooms.html',
        rooms=rooms
    )
    
@app.route('/rooms/<int:room_id>')
def room_details(room_id):

    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    # Get room information
    cursor.execute("""
        SELECT
            Room_ID,
            Room_Number,
            Status
        FROM rooms
        WHERE Room_ID = %s
    """, (room_id,))

    room = cursor.fetchone()

    if room is None:
        cursor.close()
        connection.close()
        return "Room not found", 404

    # Get beds and current students
    cursor.execute("""
        SELECT
            b.Bed_ID,
            b.Bed_Number,
            b.Status,
            s.Student_ID,
            s.First_Name,
            s.Last_Name,
            ra.Start_Date
        FROM beds b
        LEFT JOIN room_assignments ra
            ON b.Bed_ID = ra.Bed_ID
            AND ra.Status = 'Active'
        LEFT JOIN students s
            ON ra.Student_ID = s.Student_ID
        WHERE b.Room_ID = %s
        ORDER BY b.Bed_ID
    """, (room_id,))

    beds = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'room_details.html',
        room=room,
        beds=beds
    )
    
@app.route('/beds')
def beds_page():

    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            b.Bed_ID,
            b.Bed_Number,
            b.Status,
            r.Room_ID,
            r.Room_Number,
            s.Student_ID,
            s.First_Name,
            s.Last_Name,
            ra.Start_Date
        FROM beds b
        JOIN rooms r
            ON b.Room_ID = r.Room_ID
        LEFT JOIN room_assignments ra
            ON b.Bed_ID = ra.Bed_ID
            AND ra.Status = 'Active'
        LEFT JOIN students s
            ON ra.Student_ID = s.Student_ID
        ORDER BY r.Room_ID, b.Bed_ID
    """)

    beds = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'beds.html',
        beds=beds
    )
    
@app.route('/buildings')
def buildings_page():
    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            Building_ID,
            Building_Name,
            Address,
            Description,
            Status
        FROM buildings
        ORDER BY Building_ID
    """)

    buildings = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'buildings.html',
        buildings=buildings
    )
    
@app.route('/buildings/<int:building_id>/floors')
def building_floors(building_id):
    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT Building_ID, Building_Name
        FROM buildings
        WHERE Building_ID = %s
    """, (building_id,))

    building = cursor.fetchone()

    if building is None:
        cursor.close()
        connection.close()
        return "Building not found", 404

    cursor.execute("""
        SELECT Floor_ID, Floor_Name
        FROM floors
        WHERE Building_ID = %s
        ORDER BY Floor_ID
    """, (building_id,))

    floors = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'building_floors.html',
        building=building,
        floors=floors
    )
    
@app.route('/employees')
def employees_page():
    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            e.Employee_ID,
            e.Name,
            e.Father_Name,
            e.Phone,
            et.Type_Name,
            e.Salary,
            e.Hire_Date,
            e.Status
        FROM employees e
        JOIN employee_types et
            ON e.Employee_Type_ID = et.Employee_Type_ID
        ORDER BY e.Employee_ID DESC
    """)

    employees = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'employees.html',
        employees=employees
    )
    
@app.route('/employees/add', methods=['GET', 'POST'])
def add_employee():
    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        father_name = request.form.get('father_name', '').strip()
        phone = request.form.get('phone', '').strip()
        employee_type_id = request.form.get('employee_type_id')
        salary = request.form.get('salary') or None
        hire_date = request.form.get('hire_date') or None
        status = request.form.get('status', 'Active')

        if not name or not employee_type_id:
            cursor.execute("""
                SELECT Employee_Type_ID, Type_Name
                FROM employee_types
                ORDER BY Type_Name
            """)
            employee_types = cursor.fetchall()
            cursor.close()
            connection.close()

            return render_template(
                'add_employee.html',
                employee_types=employee_types,
                error="Name and position are required."
            )

        try:
            cursor.execute("""
                INSERT INTO employees
                    (Name, Father_Name, Phone, Employee_Type_ID,
                     Salary, Hire_Date, Status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                name,
                father_name or None,
                phone or None,
                int(employee_type_id),
                salary,
                hire_date,
                status
            ))

            connection.commit()
            cursor.close()
            connection.close()

            return redirect(url_for('employees_page'))

        except Exception as e:
            print("ADD EMPLOYEE ERROR:", repr(e))

            try:
                connection.rollback()
            except Exception as rollback_error:
                print("ROLLBACK ERROR:", repr(rollback_error))

            try:
                cursor.close()
            except Exception:
                pass

            try:
                connection.close()
            except Exception:
                pass

            raise

    cursor.execute("""
        SELECT Employee_Type_ID, Type_Name
        FROM employee_types
        ORDER BY Type_Name
    """)
    employee_types = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'add_employee.html',
        employee_types=employee_types
    )
    
@app.route('/employees/delete/<int:employee_id>', methods=['POST'])
def delete_employee(employee_id):
    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "DELETE FROM employees WHERE Employee_ID = %s",
            (employee_id,)
        )

        connection.commit()

        cursor.close()
        connection.close()

        return redirect(url_for('employees_page'))

    except Exception:
        connection.rollback()
        cursor.close()
        connection.close()
        raise
    
@app.route('/employees/edit/<int:employee_id>', methods=['GET', 'POST'])
def edit_employee(employee_id):
    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        father_name = request.form.get('father_name', '').strip()
        phone = request.form.get('phone', '').strip()
        employee_type_id = request.form.get('employee_type_id')
        salary = request.form.get('salary') or None
        hire_date = request.form.get('hire_date') or None
        status = request.form.get('status', 'Active')

        if not name or not employee_type_id:
            cursor.execute("""
                SELECT Employee_Type_ID, Type_Name
                FROM employee_types
                ORDER BY Type_Name
            """)
            employee_types = cursor.fetchall()

            cursor.execute("""
                SELECT Employee_ID, Name, Father_Name, Phone,
                       Employee_Type_ID, Salary, Hire_Date, Status
                FROM employees
                WHERE Employee_ID = %s
            """, (employee_id,))
            employee = cursor.fetchone()

            cursor.close()
            connection.close()

            if not employee:
                return "Employee not found", 404

            return render_template(
                'edit_employee.html',
                employee=employee,
                employee_types=employee_types,
                error="Name and position are required."
            )

        try:
            cursor.execute("""
                UPDATE employees
                SET Name = %s,
                    Father_Name = %s,
                    Phone = %s,
                    Employee_Type_ID = %s,
                    Salary = %s,
                    Hire_Date = %s,
                    Status = %s
                WHERE Employee_ID = %s
            """, (
                name,
                father_name or None,
                phone or None,
                int(employee_type_id),
                salary,
                hire_date,
                status,
                employee_id
            ))

            connection.commit()
            cursor.close()
            connection.close()

            return redirect(url_for('employees_page'))

        except Exception:
            try:
                connection.rollback()
            finally:
                cursor.close()
                connection.close()
            raise

    cursor.execute("""
        SELECT Employee_ID, Name, Father_Name, Phone,
               Employee_Type_ID, Salary, Hire_Date, Status
        FROM employees
        WHERE Employee_ID = %s
    """, (employee_id,))
    employee = cursor.fetchone()

    cursor.execute("""
        SELECT Employee_Type_ID, Type_Name
        FROM employee_types
        ORDER BY Type_Name
    """)
    employee_types = cursor.fetchall()

    cursor.close()
    connection.close()

    if not employee:
        return "Employee not found", 404

    return render_template(
        'edit_employee.html',
        employee=employee,
        employee_types=employee_types
    )
    
@app.route('/employees/details/<int:employee_id>')
def employee_details(employee_id):
    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            e.Employee_ID,
            e.Name,
            e.Father_Name,
            e.Phone,
            et.Type_Name,
            e.Salary,
            e.Hire_Date,
            e.Status
        FROM employees e
        JOIN employee_types et
            ON e.Employee_Type_ID = et.Employee_Type_ID
        WHERE e.Employee_ID = %s
    """, (employee_id,))

    employee = cursor.fetchone()

    cursor.close()
    connection.close()

    if not employee:
        return "Employee not found", 404

    return render_template(
        'employee_details.html',
        employee=employee
    )
    
@app.route('/employee-salaries', methods=['GET', 'POST'])
def employee_salaries():
    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'POST':
        employee_id = request.form.get('employee_id')
        amount = request.form.get('amount')
        payment_month = request.form.get('payment_month', '').strip()
        payment_date = request.form.get('payment_date')
        status = request.form.get('status', 'Paid')
        notes = request.form.get('notes', '').strip()

        if not employee_id or not amount or not payment_month or not payment_date:
            cursor.close()
            connection.close()
            return "Please fill in all required fields.", 400

        try:
            if float(amount) <= 0:
                cursor.close()
                connection.close()
                return "Salary amount must be greater than zero.", 400

            cursor.execute("""
                INSERT INTO employee_salary_payments
                    (Employee_ID, Amount, Payment_Month,
                     Payment_Date, Status, Notes)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                int(employee_id),
                amount,
                payment_month,
                payment_date,
                status,
                notes or None
            ))

            connection.commit()
            return redirect(url_for('employee_salaries'))

        except Exception:
            connection.rollback()
            raise

        finally:
            cursor.close()
            connection.close()

    cursor.execute("""
        SELECT Employee_ID, Name, Salary
        FROM employees
        WHERE Status = 'Active'
        ORDER BY Name
    """)
    employees = cursor.fetchall()

    cursor.execute("""
        SELECT
            sp.Salary_Payment_ID,
            e.Name,
            sp.Amount,
            sp.Payment_Month,
            sp.Payment_Date,
            sp.Status,
            sp.Notes
        FROM employee_salary_payments sp
        JOIN employees e
            ON sp.Employee_ID = e.Employee_ID
        ORDER BY sp.Payment_Date DESC, sp.Salary_Payment_ID DESC
    """)
    salary_payments = cursor.fetchall()
    
    cursor.execute("""
        SELECT
            COALESCE(SUM(CASE
                WHEN Status = 'Paid' THEN Amount
                ELSE 0
            END), 0),
            COALESCE(SUM(CASE
                WHEN Status = 'Pending' THEN Amount
                ELSE 0
            END), 0)
        FROM employee_salary_payments
        WHERE Payment_Month = %s
    """, (datetime.now().strftime('%B %Y'),))

    salary_totals = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*)
        FROM employees
        WHERE Status = 'Active'
    """)
    active_employee_count = cursor.fetchone()[0]

    cursor.close()
    connection.close()

    return render_template(
        'employee_salaries.html',
        employees=employees,
        salary_payments=salary_payments,
        paid_total=salary_totals[0],
        pending_total=salary_totals[1],
        active_employee_count=active_employee_count
    )
    
@app.route('/floors')
def floors_page():
    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT Floor_ID, Floor_Name
        FROM floors
        ORDER BY Floor_ID
    """)

    floors = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'floors.html',
        floors=floors
    )
    
@app.route('/floors/<int:floor_id>/rooms')
def floor_rooms(floor_id):

    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    # Get selected floor
    cursor.execute("""
        SELECT Floor_ID, Floor_Name
        FROM floors
        WHERE Floor_ID = %s
    """, (floor_id,))

    floor = cursor.fetchone()

    if floor is None:
        cursor.close()
        connection.close()
        return "Floor not found", 404

    # Get rooms belonging to this floor
    cursor.execute("""
        SELECT
            r.Room_ID,
            r.Room_Number,
            r.Status,
            COUNT(b.Bed_ID) AS Total_Beds,
            SUM(
                CASE
                    WHEN b.Status = 'Occupied' THEN 1
                    ELSE 0
                END
            ) AS Occupied_Beds,
            SUM(
                CASE
                    WHEN b.Status = 'Available' THEN 1
                    ELSE 0
                END
            ) AS Available_Beds
        FROM rooms r
        LEFT JOIN beds b
            ON r.Room_ID = b.Room_ID
        WHERE r.Floor_ID = %s
        GROUP BY
            r.Room_ID,
            r.Room_Number,
            r.Status
        ORDER BY r.Room_Number
    """, (floor_id,))

    rooms = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'floor_rooms.html',
        floor=floor,
        rooms=rooms
    )
    
@app.route('/assignments')
def assignments_page():

    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            ra.Assignment_ID,
            s.Student_ID,
            s.First_Name,
            s.Last_Name,
            r.Room_Number,
            b.Bed_Number,
            ra.Start_Date,
            ra.End_Date,
            ra.Status
        FROM room_assignments ra
        JOIN students s
            ON ra.Student_ID = s.Student_ID
        LEFT JOIN beds b
            ON ra.Bed_ID = b.Bed_ID
        LEFT JOIN rooms r
            ON b.Room_ID = r.Room_ID
        ORDER BY ra.Assignment_ID DESC
    """)

    assignments = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        'assignments.html',
        assignments=assignments
    )
    
@app.route('/assignments/<int:assignment_id>/end', methods=['POST'])
def end_assignment(assignment_id):

    if "user_id" not in session:
        return "Please login first", 401

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Find the active assignment and its bed
        cursor.execute("""
            SELECT Bed_ID
            FROM room_assignments
            WHERE Assignment_ID = %s
              AND Status = 'Active'
        """, (assignment_id,))

        assignment = cursor.fetchone()

        if assignment is None:
            cursor.close()
            connection.close()
            return "Active assignment not found.", 404

        bed_id = assignment[0]

        # End the assignment and preserve its history
        cursor.execute("""
            UPDATE room_assignments
            SET Status = 'Ended',
                End_Date = CURDATE()
            WHERE Assignment_ID = %s
              AND Status = 'Active'
        """, (assignment_id,))

        # Free the bed only if no other active assignment uses it
        if bed_id is not None:
            cursor.execute("""
                SELECT COUNT(*)
                FROM room_assignments
                WHERE Bed_ID = %s
                  AND Status = 'Active'
            """, (bed_id,))

            active_count = cursor.fetchone()[0]

            if active_count == 0:
                cursor.execute("""
                    UPDATE beds
                    SET Status = 'Available'
                    WHERE Bed_ID = %s
                """, (bed_id,))

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()

    return redirect('/assignments? message=ended')

@app.route('/meals')
def meals_page():
    if "user_id" not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Get meal statistics
        cursor.execute("""
            SELECT COUNT(*)
            FROM meals
            WHERE Meal_Date = CURDATE()
        """)
        today_meals = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM meal_records
            WHERE Meal_ID IN (
                SELECT Meal_ID
                FROM meals
                WHERE Meal_Date = CURDATE()
            )
        """)
        today_records = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM meal_records mr
            JOIN meals m ON mr.Meal_ID = m.Meal_ID
            WHERE m.Meal_Date = CURDATE()
              AND mr.Status = 'Received'
        """)
        received_meals = cursor.fetchone()[0]

        # Get meals and employee names
        cursor.execute("""
            SELECT
                m.Meal_ID,
                m.Meal_Type,
                m.Meal_Date,
                m.Employee_ID,
                e.Name
            FROM meals m
            LEFT JOIN employees e
                ON m.Employee_ID = e.Employee_ID
            ORDER BY m.Meal_Date DESC, m.Meal_ID DESC
        """)
        meals = cursor.fetchall()

        # Get employees
        cursor.execute("""
            SELECT Employee_ID, Name
            FROM employees
            ORDER BY Name
        """)
        employees = cursor.fetchall()

        # Get students
        cursor.execute("""
            SELECT
                Student_ID,
                CONCAT(
                    First_Name,
                    ' ',
                    COALESCE(Last_Name, '')
                ) AS Student_Name
            FROM students
            ORDER BY First_Name, Last_Name
        """)
        students = cursor.fetchall()

        # Get meal delivery history
        cursor.execute("""
            SELECT
                mr.Record_ID,
                CONCAT(
                    s.First_Name,
                    ' ',
                    COALESCE(s.Last_Name, '')
                ) AS Student_Name,
                m.Meal_Type,
                m.Meal_Date,
                mr.Status
            FROM meal_records mr
            JOIN students s
                ON mr.Student_ID = s.Student_ID
            JOIN meals m
                ON mr.Meal_ID = m.Meal_ID
            ORDER BY m.Meal_Date DESC, mr.Record_ID DESC
        """)
        meal_records = cursor.fetchall()

        return render_template(
            'meals.html',
            meals=meals,
            employees=employees,
            today_meals=today_meals,
            today_records=today_records,
            received_meals=received_meals,
            students=students,
            meal_records=meal_records
        )

    finally:
        cursor.close()
        connection.close()
        
@app.route('/expenses')
def expenses_page():
    if "user_id" not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Get total expenses
        cursor.execute("""
            SELECT COALESCE(SUM(Amount), 0)
            FROM expenses
        """)
        total_expenses = cursor.fetchone()[0]

        # Get today's expenses
        cursor.execute("""
            SELECT COALESCE(SUM(Amount), 0)
            FROM expenses
            WHERE Expense_Date = CURDATE()
        """)
        today_expenses = cursor.fetchone()[0]

        # Get this month's expenses
        cursor.execute("""
            SELECT COALESCE(SUM(Amount), 0)
            FROM expenses
            WHERE YEAR(Expense_Date) = YEAR(CURDATE())
              AND MONTH(Expense_Date) = MONTH(CURDATE())
        """)
        monthly_expenses = cursor.fetchone()[0]

        # Get expense history
        cursor.execute("""
            SELECT
                Expense_ID,
                Expense_Type,
                Amount,
                Expense_Date,
                Description
            FROM expenses
            ORDER BY Expense_Date DESC, Expense_ID DESC
        """)
        expenses = cursor.fetchall()

        return render_template(
            'expenses.html',
            expenses=expenses,
            total_expenses=total_expenses,
            today_expenses=today_expenses,
            monthly_expenses=monthly_expenses
        )

    finally:
        cursor.close()
        connection.close()
        
@app.route('/add_expense', methods=['POST'])
def add_expense():
    if "user_id" not in session:
        return redirect(url_for('login'))

    expense_type = request.form.get('expense_type', '').strip()
    amount = request.form.get('amount', '').strip()
    expense_date = request.form.get('expense_date', '').strip()
    description = request.form.get('description', '').strip()

    if not expense_type or not amount or not expense_date:
        flash('Please fill in all required fields.', 'error')
        return redirect(url_for('expenses_page'))

    try:
        amount = float(amount)

        if amount <= 0:
            flash('Amount must be greater than zero.', 'error')
            return redirect(url_for('expenses_page'))

        connection = get_db_connection()
        cursor = connection.cursor()

        try:
            cursor.execute("""
                INSERT INTO expenses
                    (User_ID, Expense_Type, Amount, Expense_Date, Description)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                session['user_id'],
                expense_type,
                amount,
                expense_date,
                description or None
            ))

            connection.commit()

        finally:
            cursor.close()
            connection.close()

        flash('Expense added successfully!', 'success')

    except (ValueError, TypeError):
        flash('Please enter a valid amount.', 'error')

    return redirect(url_for('expenses_page'))

@app.route('/delete_expense/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    if "user_id" not in session:
        return redirect(url_for('login'))

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "DELETE FROM expenses WHERE Expense_ID = %s",
            (expense_id,)
        )
        connection.commit()

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for('expenses_page'))

@app.route('/meals/add', methods=['POST'])
def add_meal():
    if "user_id" not in session:
        return "Please login first", 401

    meal_type = request.form.get('meal_type', '').strip()
    meal_date = request.form.get('meal_date', '').strip()
    employee_id = request.form.get('employee_id', '').strip()

    if meal_type not in ['Breakfast', 'Lunch', 'Dinner']:
        return "Invalid meal type", 400

    if not meal_date:
        return "Meal date is required", 400

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        if employee_id:
            cursor.execute("""
                INSERT INTO meals (Meal_Type, Meal_Date, Employee_ID)
                VALUES (%s, %s, %s)
            """, (meal_type, meal_date, employee_id))
        else:
            cursor.execute("""
                INSERT INTO meals (Meal_Type, Meal_Date, Employee_ID)
                VALUES (%s, %s, NULL)
            """, (meal_type, meal_date))

        connection.commit()
        return redirect(url_for('meals_page'))

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()
        
@app.route('/meals/record', methods=['POST'])
def record_meal():
    if "user_id" not in session:
        return "Please login first", 401

    student_id = request.form.get('student_id', '').strip()
    meal_id = request.form.get('meal_id', '').strip()
    status = request.form.get('status', '').strip()

    if not student_id.isdigit() or not meal_id.isdigit():
        return "Please select a valid student and meal", 400

    if status not in ['Received', 'Not Received']:
        return "Invalid meal status", 400

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Check that the selected student exists
        cursor.execute(
            "SELECT Student_ID FROM students WHERE Student_ID = %s",
            (student_id,)
        )
        if not cursor.fetchone():
            return "Student not found", 404

        # Check that the selected meal exists
        cursor.execute(
            "SELECT Meal_ID FROM meals WHERE Meal_ID = %s",
            (meal_id,)
        )
        if not cursor.fetchone():
            return "Meal not found", 404

        # Avoid duplicate records for the same student and meal
        cursor.execute("""
            SELECT Record_ID
            FROM meal_records
            WHERE Student_ID = %s AND Meal_ID = %s
        """, (student_id, meal_id))

        if cursor.fetchone():
            return "A record already exists for this student and meal", 409

        cursor.execute("""
            INSERT INTO meal_records (Student_ID, Meal_ID, Status)
            VALUES (%s, %s, %s)
        """, (student_id, meal_id, status))

        connection.commit()
        return redirect(url_for('meals_page'))

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route('/settings')
def settings_page():
    if "user_id" not in session:
        return redirect(url_for("home"))

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT Username, Role, Status,
            Last_Login
            FROM users
            WHERE User_ID = %s
        """, (session["user_id"],))

        user = cursor.fetchone()

        if user is None:
            session.clear()
            return redirect(url_for("home"))

        return render_template(
            "settings.html",
            username=user[0],
            role=user[1],
            status=user[2],
            last_login=user[3]
        )

    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)