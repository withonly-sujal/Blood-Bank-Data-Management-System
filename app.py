import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, request, redirect, url_for, render_template, flash
from flask_mysqldb import MySQL
import uuid
from datetime import date, datetime

app = Flask(__name__)

# --- MySQL Configuration ---
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD') 
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB', 'bloodbank_db')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor' 

app.secret_key = os.getenv('FLASK_SECRET_KEY') 
mysql = MySQL(app) # Initialize MySQL object here

# --- GLOBAL HELPER FUNCTION (Needs mysql object) ---
def get_dashboard_stats(mysql_obj):
    """Fetches donor and available blood bag counts."""
    stats = {'donor_count': 0, 'stock_count': 0}
    try:
        cur = mysql_obj.connection.cursor()
        cur.execute("SELECT COUNT(*) AS count FROM Donor;")
        stats['donor_count'] = cur.fetchone()['count']
        cur.execute("SELECT COUNT(*) AS count FROM Blood_Bag WHERE status = 'Available';")
        stats['stock_count'] = cur.fetchone()['count']
        cur.close()
    except Exception as e:
        # This print is for terminal debugging only
        print(f"Error fetching dashboard stats: {e}") 
    return stats


# --- 1. CORE ROUTES ---

@app.route('/')
def index():
    stats = get_dashboard_stats(mysql)
    return render_template('index.html', stats=stats)


# --- 2. CREATE OPERATIONS (Donor and Donation) ---

@app.route('/donor/add', methods=['GET', 'POST'])
def add_donor():
    if request.method == 'POST':
        details = request.form
        fname = details['first_name']
        lname = details['last_name']
        dob = details['dob'] 
        gender = details['gender']
        phone = details['phone']
        bgroup = details['blood_group']

        sql_insert = """
            INSERT INTO Donor (first_name, last_name, date_of_birth, gender, phone_number, blood_group)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        values = (fname, lname, dob, gender, phone, bgroup)

        try:
            cur = mysql.connection.cursor()
            cur.execute(sql_insert, values) 
            mysql.connection.commit()
            new_donor_id = cur.lastrowid
            cur.close()
            
            flash(f"Donor ID {new_donor_id} Registered. Now, record the donation!", 'success')
            return redirect(url_for('record_donation', donor_id=new_donor_id))

        except Exception as e:
            stats = get_dashboard_stats(mysql)
            flash(f"Error: Could not register donor. Details: {e}", 'error')
            # Pass stats when re-rendering on error
            return render_template('add_donor.html', stats=stats)

    # GET Request
    stats = get_dashboard_stats(mysql)
    return render_template('add_donor.html', stats=stats)


# app.py

@app.route('/donation/record', defaults={'donor_id': None}, methods=['GET', 'POST'])
@app.route('/donation/record/<int:donor_id>', methods=['GET', 'POST'])
def record_donation(donor_id):
    staff_options = [{'staff_id': 1, 'name': 'Dr. Singh (Manager)'}, {'staff_id': 2, 'name': 'Nurse Priya'}] 
    stats = get_dashboard_stats(mysql)
    
    if request.method == 'POST':
        details = request.form
        donor_id = details['donor_id']
        staff_id = details['staff_id']
        units_donated = int(details['units_donated']) # Get the new units field
        donation_date_str = details['donation_date']
        
        # --- SERVER-SIDE VALIDATION CHECK (Critical for security) ---
        if units_donated > 3:
            flash("Error: Cannot donate more than 3 units in a single session.", 'error')
            return render_template('record_donation.html', donor_id=donor_id, staff_options=staff_options, stats=stats, now=datetime.now())
        # -----------------------------------------------------------

        try:
            cur = mysql.connection.cursor()
            
            # 1. Get Donor Blood Group
            cur.execute("SELECT blood_group FROM Donor WHERE donor_id = %s", [donor_id])
            donor_result = cur.fetchone()
            if not donor_result:
                raise Exception(f"Donor ID {donor_id} not found.")
            blood_group = donor_result['blood_group']

            donation_date = datetime.strptime(donation_date_str, '%Y-%m-%d').date()
            expiry_date = donation_date.replace(year=donation_date.year + 1)
            
            # --- CORE FIX: LOOP AND INSERT ONE RECORD PER UNIT ---
            bags_recorded = 0
            for i in range(units_donated):
                bag_id = f"BAG-{blood_group}-{str(uuid.uuid4())[:5].upper()}-{i+1}" # Unique ID for each bag
                
                # Insert into Blood_Bag (Status defaults to 'Quarantined')
                sql_bag = """
                    INSERT INTO Blood_Bag (bag_id, blood_group, donation_date, expiry_date, donor_id)
                    VALUES (%s, %s, %s, %s, %s)
                """
                cur.execute(sql_bag, (bag_id, blood_group, donation_date, expiry_date, donor_id))

                # Insert into Donation_Transaction (THIS IS WHERE THE TRIGGER FIRES FOR EACH BAG)
                sql_trans = """
                    INSERT INTO Donation_Transaction (donor_id, staff_id, bag_id)
                    VALUES (%s, %s, %s)
                """
                cur.execute(sql_trans, (donor_id, staff_id, bag_id))
                bags_recorded += 1
            
            mysql.connection.commit()
            cur.close()
            
            flash(f"Success! {bags_recorded} units recorded. Stock updated (Trigger Verified {bags_recorded} times).", 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            mysql.connection.rollback()
            flash(f"Donation failed. Error: {e}", 'error')
            
    # GET Request (or Error Re-render)
    return render_template('record_donation.html', donor_id=donor_id, staff_options=staff_options, stats=stats, now=datetime.now())


# --- 3. READ OPERATIONS (Stored Procedure and View) ---

@app.route('/report/stock')
def get_stock_report():
    groups_to_check = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-'] # Added more groups for comprehensive report
    stock_report = {}
    
    try:
        cur = mysql.connection.cursor()
        
        for group in groups_to_check:
            cur.execute("CALL Get_Available_Blood_Units(%s, @stock_count);", [group])
            cur.execute("SELECT @stock_count;")
            result = cur.fetchone()
            stock_report[group] = result['@stock_count'] if result else 0
            
        cur.close()
        flash("Stock report generated using Stored Procedure.", 'success')
        
    except Exception as e:
        flash(f"Error fetching report: {e}", 'error')

    stats = get_dashboard_stats(mysql)
    return render_template('stock_report.html', stock_report=stock_report, stats=stats)


@app.route('/report/eligible_donors')
def list_eligible_donors():
    eligible_donors = []
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT donor_id, first_name, last_name, blood_group, last_donation_date FROM Eligible_Donors;")
        eligible_donors = cur.fetchall()
        cur.close()
        flash("Eligible donor list pulled directly from the SQL VIEW.", 'success')
        
    except Exception as e:
        flash(f"Error querying eligible donors view: {e}", 'error')

    stats = get_dashboard_stats(mysql)
    return render_template('eligible_donors.html', donors=eligible_donors, stats=stats)

# app.py (Add this new function)

@app.route('/report/all_donors')
def list_all_donors():
    all_donors = []
    try:
        cur = mysql.connection.cursor()
        # Simple SELECT without any join or complex filtering
        cur.execute("SELECT donor_id, first_name, last_name, blood_group, phone_number FROM Donor ORDER BY donor_id;")
        all_donors = cur.fetchall()
        cur.close()
        flash("Displaying all registered donors.", 'success')
        
    except Exception as e:
        flash(f"Error querying all donors: {e}", 'error')

    stats = get_dashboard_stats(mysql)
    return render_template('all_donors.html', donors=all_donors, stats=stats)

# --- 4. Request Blood ---
@app.route('/request/add', methods=['GET', 'POST'])
def request_blood():
    staff_options = [{'staff_id': 1, 'name': 'Dr. Singh (Manager)'}, {'staff_id': 2, 'name': 'Nurse Priya'}]
    if request.method == 'POST':
        details = request.form
        patient_name = details['patient_name']
        hospital = details['hospital']
        required_group = details['required_group']
        units = details['units']
        
        try:
            cur = mysql.connection.cursor()
            
            # 1. Insert Recipient
            sql_recipient = """
                INSERT INTO Recipient (name, hospital_name, required_blood_group)
                VALUES (%s, %s, %s)
            """
            cur.execute(sql_recipient, (patient_name, hospital, required_group))
            patient_id = cur.lastrowid
            
            # 2. Insert Blood Request
            sql_request = """
                INSERT INTO Blood_Request (patient_id, requested_group, units_requested, fulfillment_status)
                VALUES (%s, %s, %s, 'Pending')
            """
            cur.execute(sql_request, (patient_id, required_group, units))
            request_id = cur.lastrowid
            
            mysql.connection.commit()
            cur.close()
            
            flash(f"Request ID {request_id} created for {patient_name}. Attempting fulfillment...", 'success')
            
            # Immediately redirect to the fulfillment attempt
            return redirect(url_for('fulfill_request', request_id=request_id))
        
        except Exception as e:
            mysql.connection.rollback()
            flash(f"Error creating request: {e}", 'error')
        
    stats = get_dashboard_stats(mysql)
    return render_template('request_blood.html', stats=stats, staff_options=staff_options)
            
# app.py

@app.route('/request/fulfill/<int:request_id>')
def fulfill_request(request_id):
    try:
        cur = mysql.connection.cursor()
        
        # 1. Get Request Details (READ)
        cur.execute("SELECT * FROM Blood_Request WHERE request_id = %s", [request_id])
        request_details = cur.fetchone()
        
        if not request_details:
            flash("Request not found.", 'error')
            return redirect(url_for('index'))

        required_group = request_details['requested_group']
        units_needed = request_details['units_requested']

        # 2. Check Available Stock (READ)
        # Find the oldest available bag that matches the group
        sql_find_bag = """
            SELECT bag_id 
            FROM Blood_Bag 
            WHERE blood_group = %s AND status = 'Available' 
            ORDER BY expiry_date ASC 
            LIMIT %s
        """
        cur.execute(sql_find_bag, (required_group, units_needed))
        available_bags = cur.fetchall()
        
        if len(available_bags) >= units_needed:
            # --- STOCK IS AVAILABLE: FULFILL THE REQUEST (UPDATE/DELETE) ---
            bag_ids_to_use = [bag['bag_id'] for bag in available_bags]

            # a. Update Blood Bags (UPDATE)
            sql_update_bags = f"""
                UPDATE Blood_Bag 
                SET status = 'Used' 
                WHERE bag_id IN ({', '.join(['%s'] * len(bag_ids_to_use))})
            """
            cur.execute(sql_update_bags, tuple(bag_ids_to_use))

            # b. Update Request Status (UPDATE)
            sql_update_request = """
                UPDATE Blood_Request 
                SET fulfillment_status = 'Fulfilled' 
                WHERE request_id = %s
            """
            cur.execute(sql_update_request, [request_id])
            
            mysql.connection.commit()
            flash(f"SUCCESS! Fulfilled Request ID {request_id}. {len(bag_ids_to_use)} units of {required_group} stock used.", 'success')

        else:
            # --- STOCK UNAVAILABLE: MARK AS PENDING/REJECTED (UPDATE) ---
            sql_update_request = """
                UPDATE Blood_Request 
                SET fulfillment_status = 'Rejected' 
                WHERE request_id = %s
            """
            cur.execute(sql_update_request, [request_id])
            mysql.connection.commit()
            flash(f"FAILED. Not enough {required_group} units in stock. Request ID {request_id} rejected.", 'error')

        cur.close()
        
    except Exception as e:
        mysql.connection.rollback()
        flash(f"An unexpected error occurred during fulfillment: {e}", 'error')

    return redirect(url_for('index'))
        
# --- 5. RUNNER ---

if __name__ == '__main__':
    app.run(debug=True)