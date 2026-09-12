from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from config import DB_CONFIG

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # any random string


# ---------- Database Connection ----------
def get_db_connection():
    return mysql.connector.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        database=DB_CONFIG['database']
    )


# ---------- HOME ----------
@app.route('/')
def home():
    return render_template('home.html')

# ---------- REGISTER ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor()

        # Insert into USER
        cursor.execute(
            "INSERT INTO USER (Name, Email, Password, Role) VALUES (%s, %s, %s, %s)",
            (name, email, hashed_password, role)
        )

        # 🔑 Get the new user's ID
        user_id = cursor.lastrowid

        # 🔁 Insert into role-specific table
        if role == 'Customer':
            cursor.execute(
                "INSERT INTO CUSTOMER (User_id) VALUES (%s)",
                (user_id,)
            )
        elif role == 'Staff':
            cursor.execute(
                "INSERT INTO STAFF (User_id) VALUES (%s)",
                (user_id,)
            )

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('login'))

    return render_template('register.html')


# ---------- LOGIN ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM USER WHERE Email=%s", (email,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user and check_password_hash(user['Password'], password):
            session['user_id'] = user['User_id']
            session['role'] = user['Role']

            if user['Role'] == 'Admin':
                return redirect(url_for('admin_dashboard'))
            elif user['Role'] == 'Staff':
                return redirect(url_for('staff_dashboard'))
            else:
                return redirect(url_for('customer_dashboard'))

        return "Invalid email or password"

    return render_template('login.html')


# ---------- DASHBOARDS ----------
@app.route('/admin_dashboard')
def admin_dashboard():
    if session.get('role') != 'Admin':
        return "Access Denied"
    return render_template('admin_dashboard.html')


# ---------- STAFF DASHBOARD ----------
@app.route('/staff_dashboard')
def staff_dashboard():
    if session.get('role') != 'Staff':
        return "Access Denied"

    user_id = session.get('user_id')  # USER ID of the logged-in staff

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Find Staff_id corresponding to this user
    cursor.execute("SELECT Staff_id FROM STAFF WHERE User_id=%s", (user_id,))
    staff_row = cursor.fetchone()
    if not staff_row:
        cursor.close()
        conn.close()
        return "Staff record not found"
    staff_id = staff_row['Staff_id']

    # Get appointments
    cursor.execute("""
        SELECT a.Appointment_id, a.Date, a.Time, a.Status,
               u.Name AS Customer_name
        FROM APPOINTMENTS a
        JOIN CUSTOMER c ON a.Customer_id = c.Customer_id
        JOIN USER u ON c.User_id = u.User_id
        WHERE a.Staff_id = %s
        ORDER BY a.Date, a.Time
    """, (staff_id,))

    appointments = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('staff_dashboard.html', appointments=appointments)



# ---------- STAFF: UPDATE APPOINTMENT STATUS ----------

@app.route('/update_appointment_status/<int:appointment_id>')
def update_appointment_status(appointment_id):
    if session.get('role') != 'Staff':
        return "Access Denied"

    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get Staff_id
    cursor.execute("SELECT Staff_id FROM STAFF WHERE User_id=%s", (user_id,))
    staff_row = cursor.fetchone()
    if not staff_row:
        cursor.close()
        conn.close()
        return "Staff record not found"
    staff_id = staff_row[0]

    # Update only if this staff is assigned
    cursor.execute("""
        UPDATE APPOINTMENTS
        SET Status='Completed'
        WHERE Appointment_id=%s AND Staff_id=%s
    """, (appointment_id, staff_id))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('staff_dashboard'))

# ---------- CUSTOMER DASHBOARD ----------
@app.route('/customer_dashboard')
def customer_dashboard():
    if session.get('role') != 'Customer':
        return "Access Denied"

    user_id = session.get('user_id')  # Get logged-in user's ID

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Find Customer_id corresponding to this user
    cursor.execute("SELECT Customer_id FROM CUSTOMER WHERE User_id=%s", (user_id,))
    customer_row = cursor.fetchone()
    if not customer_row:
        cursor.close()
        conn.close()
        return "Customer record not found"
    customer_id = customer_row['Customer_id']

    # Get appointments for this customer
    cursor.execute("""
        SELECT a.Appointment_id, a.Date, a.Time, a.Status,
               u.Name AS Staff_name
        FROM APPOINTMENTS a
        JOIN STAFF s ON a.Staff_id = s.Staff_id
        JOIN USER u ON s.User_id = u.User_id
        WHERE a.Customer_id = %s
        ORDER BY a.Date, a.Time
    """, (customer_id,))

    appointments = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('customer_dashboard.html', appointments=appointments)

# ---------- CUSTOMER VIEW SERVICES ----------

@app.route('/view_services')
def view_services():
    if session.get('role') != 'Customer':
        return "Access Denied"

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM SERVICE")
    services = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('view_services.html', services=services)

# ---------- CUSTOMER: BOOK APPOINTMENT ----------
@app.route('/book_appointment', methods=['GET', 'POST'])
def book_appointment():
    if session.get('role') != 'Customer':
        return "Access Denied"

    user_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1️⃣ Get customer_id
    cursor.execute("SELECT Customer_id FROM CUSTOMER WHERE User_id=%s", (user_id,))
    customer_row = cursor.fetchone()
    if not customer_row:
        cursor.close()
        conn.close()
        return "Customer record not found"
    customer_id = customer_row['Customer_id']

    # 2️⃣ Get staff list
    cursor.execute("SELECT s.Staff_id, u.Name FROM STAFF s JOIN USER u ON s.User_id = u.User_id")
    staff_list = cursor.fetchall()

    # 3️⃣ Get services list
    cursor.execute("SELECT Service_id, Service_name, Price FROM SERVICE")
    services = cursor.fetchall()

    if request.method == 'POST':
        staff_id = request.form['staff_id']
        selected_services = request.form.getlist('service_id')  # 🔹 multiple services
        date = request.form['date']
        time = request.form['time']

        # 4️⃣ Create appointment
        cursor.execute("""
            INSERT INTO APPOINTMENTS (Customer_id, Staff_id, Date, Time, Status)
            VALUES (%s, %s, %s, %s, 'Pending')
        """, (customer_id, staff_id, date, time))
        appointment_id = cursor.lastrowid

        # 5️⃣ Attach all selected services and calculate total
        total_amount = 0
        for service_id in selected_services:
            cursor.execute("""
                INSERT INTO APPOINTMENT_SERVICES (Appointment_id, Service_id)
                VALUES (%s, %s)
            """, (appointment_id, service_id))

            cursor.execute("SELECT Price FROM SERVICE WHERE Service_id=%s", (service_id,))
            price_row = cursor.fetchone()
            total_amount += price_row['Price'] if price_row else 0

        # 6️⃣ Create bill automatically
        cursor.execute("""
            INSERT INTO BILL (Appointment_id, Amount, Payment_status)
            VALUES (%s, %s, 'Unpaid')
        """, (appointment_id, total_amount))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('customer_dashboard'))

    cursor.close()
    conn.close()
    return render_template('book_appointment.html', staff_list=staff_list, services=services)


# ---------- CUSTOMER: VIEW BILLS ----------
@app.route('/customer_bills')
def customer_bills():
    if session.get('role') != 'Customer':
        return "Access Denied"

    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get customer_id of logged-in user
    cursor.execute("SELECT Customer_id FROM CUSTOMER WHERE User_id=%s", (user_id,))
    customer_row = cursor.fetchone()
    if not customer_row:
        cursor.close()
        conn.close()
        return "Customer record not found"
    customer_id = customer_row['Customer_id']

    # Get bills for this customer
    cursor.execute("""
        SELECT b.Bill_id, a.Appointment_id, u_s.Name AS Staff_name,
               b.Amount, b.Payment_status, b.Payment_method, b.Created_at
        FROM BILL b
        JOIN APPOINTMENTS a ON b.Appointment_id = a.Appointment_id
        JOIN STAFF s ON a.Staff_id = s.Staff_id
        JOIN USER u_s ON s.User_id = u_s.User_id
        WHERE a.Customer_id = %s
        ORDER BY b.Created_at DESC
    """, (customer_id,))
    bills = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('customer_bills.html', bills=bills)


# ----------CANCEL APPOINTMENT----------
@app.route('/cancel_appointment/<int:appointment_id>')
def cancel_appointment(appointment_id):
    # Ensure only customers can cancel
    if session.get('role') != 'Customer':
        return "Access Denied"

    user_id = session.get('user_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get Customer_id
    cursor.execute("SELECT Customer_id FROM CUSTOMER WHERE User_id=%s", (user_id,))
    customer_row = cursor.fetchone()
    if not customer_row:
        cursor.close()
        conn.close()
        return "Customer record not found"
    customer_id = customer_row[0]

    # Cancel only if this appointment belongs to this customer
    cursor.execute("""
        UPDATE APPOINTMENTS
        SET Status='Cancelled'
        WHERE Appointment_id=%s AND Customer_id=%s
    """, (appointment_id, customer_id))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('customer_dashboard'))


# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.clear()  # clears all session data
    return redirect(url_for('login'))

# ---------- ADMIN: VIEW SERVICES ----------
@app.route('/services')
def services():
    if session.get('role') != 'Admin':
        return "Access Denied"

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM SERVICE")
    services = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('services.html', services=services)


# ---------- ADMIN: ADD SERVICE ----------
@app.route('/add_service', methods=['GET', 'POST'])
def add_service():
    if session.get('role') != 'Admin':
        return "Access Denied"

    if request.method == 'POST':
        name = request.form['service_name']
        price = request.form['price']
        duration = request.form['duration']

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO SERVICE (Service_name, Price, Duration) VALUES (%s, %s, %s)",
            (name, price, duration)
        )

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('services'))

    return render_template('add_service.html')


# ---------- ADMIN: EDIT SERVICE ----------
@app.route('/edit_service/<int:service_id>', methods=['GET', 'POST'])
def edit_service(service_id):
    if session.get('role') != 'Admin':
        return "Access Denied"

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form['service_name']
        price = request.form['price']
        duration = request.form['duration']

        cursor.execute(
            "UPDATE SERVICE SET Service_name=%s, Price=%s, Duration=%s WHERE Service_id=%s",
            (name, price, duration, service_id)
        )

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('services'))

    cursor.execute("SELECT * FROM SERVICE WHERE Service_id=%s", (service_id,))
    service = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template('edit_service.html', service=service)

# ---------- ADMIN: ADD APPOINTMENT ----------
@app.route('/add_appointment', methods=['GET', 'POST'])
def add_appointment():
    if session.get('role') != 'Admin':
        return "Access Denied"

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1️⃣ Fetch all customers
    cursor.execute("""
        SELECT c.Customer_id, u.Name 
        FROM CUSTOMER c 
        JOIN USER u ON c.User_id = u.User_id
    """)
    customers = cursor.fetchall()

    # 2️⃣ Fetch all staff
    cursor.execute("""
        SELECT s.Staff_id, u.Name 
        FROM STAFF s 
        JOIN USER u ON s.User_id = u.User_id
    """)
    staff_list = cursor.fetchall()

    # 3️⃣ Fetch all services
    cursor.execute("SELECT Service_id, Service_name, Price FROM SERVICE")
    services = cursor.fetchall()

    if request.method == 'POST':
        customer_id = request.form['customer_id']
        staff_id = request.form['staff_id']
        selected_services = request.form.getlist('service_id')  # 🔹 multiple services
        date = request.form['date']
        time = request.form['time']

        # 4️⃣ Create appointment
        cursor.execute("""
            INSERT INTO APPOINTMENTS (Customer_id, Staff_id, Date, Time, Status)
            VALUES (%s, %s, %s, %s, 'Pending')
        """, (customer_id, staff_id, date, time))
        appointment_id = cursor.lastrowid

        # 5️⃣ Attach all selected services and calculate total
        total_amount = 0
        for service_id in selected_services:
            cursor.execute("""
                INSERT INTO APPOINTMENT_SERVICES (Appointment_id, Service_id)
                VALUES (%s, %s)
            """, (appointment_id, service_id))

            cursor.execute("SELECT Price FROM SERVICE WHERE Service_id=%s", (service_id,))
            price_row = cursor.fetchone()
            total_amount += price_row['Price'] if price_row else 0

        # 6️⃣ Create bill automatically
        cursor.execute("""
            INSERT INTO BILL (Appointment_id, Amount, Payment_status)
            VALUES (%s, %s, 'Unpaid')
        """, (appointment_id, total_amount))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('admin_dashboard'))

    cursor.close()
    conn.close()
    return render_template(
        'add_appointment.html',
        customers=customers,
        staff_list=staff_list,
        services=services
    )


# ---------- ADMIN: EDIT APPOINTMENT ----------
@app.route('/edit_appointment/<int:appointment_id>', methods=['GET', 'POST'])
def edit_appointment(appointment_id):
    if session.get('role') != 'Admin':
        return "Access Denied"

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get appointment details
    cursor.execute("""
        SELECT a.*, c.Customer_id, u_c.Name AS Customer_name,
               s.Staff_id, u_s.Name AS Staff_name
        FROM APPOINTMENTS a
        JOIN CUSTOMER c ON a.Customer_id = c.Customer_id
        JOIN USER u_c ON c.User_id = u_c.User_id
        JOIN STAFF s ON a.Staff_id = s.Staff_id
        JOIN USER u_s ON s.User_id = u_s.User_id
        WHERE a.Appointment_id=%s
    """, (appointment_id,))
    appointment = cursor.fetchone()

    # Get all customers and staff for dropdowns
    cursor.execute("SELECT c.Customer_id, u.Name FROM CUSTOMER c JOIN USER u ON c.User_id = u.User_id")
    customers = cursor.fetchall()

    cursor.execute("SELECT s.Staff_id, u.Name FROM STAFF s JOIN USER u ON s.User_id = u.User_id")
    staff_list = cursor.fetchall()

    if request.method == 'POST':
        customer_id = request.form['customer_id']
        staff_id = request.form['staff_id']
        date = request.form['date']
        time = request.form['time']
        status = request.form['status']

        cursor.execute("""
            UPDATE APPOINTMENTS
            SET Customer_id=%s, Staff_id=%s, Date=%s, Time=%s, Status=%s
            WHERE Appointment_id=%s
        """, (customer_id, staff_id, date, time, status, appointment_id))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('admin_appointments'))

    cursor.close()
    conn.close()
    return render_template('edit_appointment.html', appointment=appointment, customers=customers, staff_list=staff_list)

# ---------- ADMIN: VIEW BILLS ----------
@app.route('/admin_bills')
def admin_bills():
    # Only Admin can access
    if session.get('role') != 'Admin':
        return "Access Denied"

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch bills with customer, staff, and appointment info
    cursor.execute("""
        SELECT b.Bill_id, a.Appointment_id, u_c.Name AS Customer_name, u_s.Name AS Staff_name,
               b.Amount, b.Payment_status, b.Payment_method, b.Created_at
        FROM BILL b
        JOIN APPOINTMENTS a ON b.Appointment_id = a.Appointment_id
        JOIN CUSTOMER c ON a.Customer_id = c.Customer_id
        JOIN USER u_c ON c.User_id = u_c.User_id
        JOIN STAFF s ON a.Staff_id = s.Staff_id
        JOIN USER u_s ON s.User_id = u_s.User_id
        ORDER BY b.Created_at DESC
    """)
    bills = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('admin_bills.html', bills=bills)


# ---------- ADMIN: MARK BILL AS PAID ----------
@app.route('/mark_bill_paid/<int:bill_id>', methods=['GET', 'POST'])
def mark_bill_paid(bill_id):
    if session.get('role') != 'Admin':
        return "Access Denied"

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get bill info
    cursor.execute("SELECT * FROM BILL WHERE Bill_id=%s", (bill_id,))
    bill = cursor.fetchone()
    if not bill:
        cursor.close()
        conn.close()
        return "Bill not found"

    if request.method == 'POST':
        payment_method = request.form['payment_method']

        # Update bill
        cursor.execute("""
            UPDATE BILL
            SET Payment_status='Paid', Payment_method=%s
            WHERE Bill_id=%s
        """, (payment_method, bill_id))
        conn.commit()

        cursor.close()
        conn.close()
        return redirect(url_for('admin_bills'))

    cursor.close()
    conn.close()
    return render_template('mark_bill_paid.html', bill=bill)

# ---------- ADMIN: DELETE SERVICE ----------
@app.route('/delete_service/<int:service_id>')
def delete_service(service_id):
    if session.get('role') != 'Admin':
        return "Access Denied"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM SERVICE WHERE Service_id=%s",
        (service_id,)
    )
    conn.commit()

    cursor.close()
    conn.close()

    return redirect(url_for('services'))

# ---------- ADMIN: DELETE APPOINTMENT ----------
@app.route('/delete_appointment/<int:appointment_id>')
def delete_appointment(appointment_id):
    if session.get('role') != 'Admin':
        return "Access Denied"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM APPOINTMENTS WHERE Appointment_id=%s",
        (appointment_id,)
    )
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('admin_appointments'))


# ---------- ADMIN: VIEW ALL APPOINTMENTS ----------
@app.route('/admin_appointments')
def admin_appointments():
    if session.get('role') != 'Admin':
        return "Access Denied"

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch all appointments with customer & staff names
    cursor.execute("""
        SELECT a.Appointment_id, a.Date, a.Time, a.Status,
               c.Customer_id, u_c.Name AS Customer_name,
               s.Staff_id, u_s.Name AS Staff_name
        FROM APPOINTMENTS a
        JOIN CUSTOMER c ON a.Customer_id = c.Customer_id
        JOIN USER u_c ON c.User_id = u_c.User_id
        JOIN STAFF s ON a.Staff_id = s.Staff_id
        JOIN USER u_s ON s.User_id = u_s.User_id
        ORDER BY a.Date, a.Time
    """)

    appointments = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('admin_appointments.html', appointments=appointments)


# ---------- RUN APP ----------
if __name__ == '__main__':
    app.run(debug=True)
