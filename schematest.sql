-- ===================================
-- SCHEMA CLEANUP AND SETUP
-- Note: Tables are NOT DROPPED to preserve test data, 
-- but routines are dropped to allow re-creation.
-- ===================================
SET FOREIGN_KEY_CHECKS = 0;
DROP PROCEDURE IF EXISTS Get_Available_Blood_Units;
DROP PROCEDURE IF EXISTS Update_Expired_Bags;
DROP FUNCTION IF EXISTS Check_Donor_Status; 
DROP VIEW IF EXISTS Eligible_Donors; 
SET FOREIGN_KEY_CHECKS = 1;


-- ===================================
-- 1. TABLE CREATION (6 Tables)
-- Note: These CREATE TABLE statements must be present 
-- even if they already exist, as they define the schema.
-- ===================================

-- 1. Donor Table
CREATE TABLE IF NOT EXISTS Donor (
    donor_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    date_of_birth DATE NOT NULL,
    gender ENUM('Male', 'Female', 'Other') NOT NULL,
    phone_number VARCHAR(10) UNIQUE NOT NULL,
    address TEXT,
    blood_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') NOT NULL
);

-- 2. Staff Table
CREATE TABLE IF NOT EXISTS Staff (
    staff_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    role VARCHAR(50) NOT NULL, 
    phone_number VARCHAR(15) UNIQUE NOT NULL
);

-- 3. Blood_Bag (Inventory) Table
CREATE TABLE IF NOT EXISTS Blood_Bag (
    bag_id VARCHAR(20) PRIMARY KEY,
    blood_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') NOT NULL,
    donation_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    status ENUM('Available', 'Quarantined', 'Used', 'Expired') NOT NULL DEFAULT 'Quarantined',
    donor_id INT,
    FOREIGN KEY (donor_id) REFERENCES Donor(donor_id),
    CHECK (expiry_date > donation_date)
);

-- 4. Donation_Transaction Table
CREATE TABLE IF NOT EXISTS Donation_Transaction (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    donor_id INT NOT NULL,
    staff_id INT NOT NULL,
    bag_id VARCHAR(20) UNIQUE NOT NULL, 
    transaction_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (donor_id) REFERENCES Donor(donor_id),
    FOREIGN KEY (staff_id) REFERENCES Staff(staff_id),
    FOREIGN KEY (bag_id) REFERENCES Blood_Bag(bag_id)
);

-- 5. Recipient (Patient) Table
CREATE TABLE IF NOT EXISTS Recipient (
    patient_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    hospital_name VARCHAR(100),
    required_blood_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') NOT NULL
);

-- 6. Blood_Request Table
CREATE TABLE IF NOT EXISTS Blood_Request (
    request_id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    requested_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') NOT NULL,
    units_requested INT NOT NULL,
    request_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fulfillment_status ENUM('Pending', 'Fulfilled', 'Rejected') NOT NULL DEFAULT 'Pending',
    FOREIGN KEY (patient_id) REFERENCES Recipient(patient_id),
    CHECK (units_requested > 0)
);


-- ===================================
-- 2. ADVANCED ROUTINES (PL/SQL)
-- ===================================

-- TRIGGER: Sets status to 'Available' after successful donation insert
DELIMITER //
CREATE TRIGGER after_donation_insert
AFTER INSERT ON Donation_Transaction
FOR EACH ROW
BEGIN
    UPDATE Blood_Bag
    SET status = 'Available'
    WHERE bag_id = NEW.bag_id;
END; //
DELIMITER ;

-- STORED PROCEDURE: Get available stock (Set-based logic)
DELIMITER //
CREATE PROCEDURE Get_Available_Blood_Units(
    IN blood_grp_param VARCHAR(5),
    OUT available_units INT
)
BEGIN
    SELECT COUNT(bag_id)
    INTO available_units
    FROM Blood_Bag
    WHERE blood_group = blood_grp_param
      AND status = 'Available'
      AND expiry_date >= CURDATE();
END; //
DELIMITER ;

-- NEW: EXPLICIT CURSOR PROCEDURE (Metric #3: Cursors/PL/SQL)
DELIMITER //

CREATE PROCEDURE Update_Expired_Bags()
BEGIN
    -- 1. Declare control variables
    DECLARE done INT DEFAULT FALSE;
    DECLARE bagID VARCHAR(20);

    -- 2. Declare the cursor: selects AVAILABLE bags that have expired
    DECLARE expired_bags_cursor CURSOR FOR 
        SELECT bag_id 
        FROM Blood_Bag 
        WHERE status = 'Available' AND expiry_date < CURDATE();

    -- 3. Declare handler for 'NOT FOUND' (exit condition)
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;

    -- 4. Open the cursor
    OPEN expired_bags_cursor;

    -- 5. Start the loop (Row-by-Row Processing)
    read_loop: LOOP
        -- Fetch the next row's bag_id into the variable
        FETCH expired_bags_cursor INTO bagID;

        -- Exit loop when no more rows are available
        IF done THEN
            LEAVE read_loop;
        END IF;

        -- 6. Perform Row-by-Row Update (The action requiring the cursor)
        UPDATE Blood_Bag
        SET status = 'Expired'
        WHERE bag_id = bagID;

    END LOOP;

    -- 7. Close and Commit
    CLOSE expired_bags_cursor;
    COMMIT; 
END //

DELIMITER ;

-- VIEW: Filters eligible donors (Reporting logic)
CREATE VIEW Eligible_Donors AS
SELECT
    d.donor_id,
    d.first_name,
    d.last_name,
    d.blood_group,
    d.phone_number,
    MAX(t.transaction_date) AS last_donation_date
FROM
    Donor d
LEFT JOIN
    Donation_Transaction t ON d.donor_id = t.donor_id
GROUP BY
    d.donor_id, d.first_name, d.last_name, d.blood_group, d.phone_number
HAVING
    last_donation_date IS NULL
    OR
    MAX(t.transaction_date) < DATE_SUB(CURDATE(), INTERVAL 90 DAY)
ORDER BY
    last_donation_date ASC;