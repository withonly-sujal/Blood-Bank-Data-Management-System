-- ---------------------------------
-- 1. Donor Table
-- ---------------------------------
CREATE TABLE Donor (
    donor_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    date_of_birth DATE NOT NULL,
    gender ENUM('Male', 'Female', 'Other') NOT NULL,
    phone_number VARCHAR(15) UNIQUE NOT NULL,
    address TEXT,
    blood_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') NOT NULL
);

-- ---------------------------------
-- 2. Staff Table
-- ---------------------------------
CREATE TABLE Staff (
    staff_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    role VARCHAR(50) NOT NULL, 
    phone_number VARCHAR(15) UNIQUE NOT NULL
);

-- ---------------------------------
-- 3. Blood_Bag (Inventory) Table
-- ---------------------------------
CREATE TABLE Blood_Bag (
    bag_id VARCHAR(20) PRIMARY KEY,
    blood_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') NOT NULL,
    donation_date DATE NOT NULL,
    expiry_date DATE NOT NULL,
    status ENUM('Available', 'Quarantined', 'Used', 'Expired') NOT NULL DEFAULT 'Quarantined',
    donor_id INT,
    FOREIGN KEY (donor_id) REFERENCES Donor(donor_id),
    CHECK (expiry_date > donation_date)
);

-- ---------------------------------
-- 4. Donation_Transaction Table
-- ---------------------------------
CREATE TABLE Donation_Transaction (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    donor_id INT NOT NULL,
    staff_id INT NOT NULL,
    bag_id VARCHAR(20) UNIQUE NOT NULL, 
    transaction_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (donor_id) REFERENCES Donor(donor_id),
    FOREIGN KEY (staff_id) REFERENCES Staff(staff_id),
    FOREIGN KEY (bag_id) REFERENCES Blood_Bag(bag_id)
);

-- ---------------------------------
-- 5. Recipient (Patient) Table
-- ---------------------------------
CREATE TABLE Recipient (
    patient_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    hospital_name VARCHAR(100),
    required_blood_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') NOT NULL
);

-- ---------------------------------
-- 6. Blood_Request Table
-- ---------------------------------
CREATE TABLE Blood_Request (
    request_id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    requested_group ENUM('O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-') NOT NULL,
    units_requested INT NOT NULL,
    request_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fulfillment_status ENUM('Pending', 'Fulfilled', 'Rejected') NOT NULL DEFAULT 'Pending',
    FOREIGN KEY (patient_id) REFERENCES Recipient(patient_id),
    CHECK (units_requested > 0)
);


-- TRIGGER
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

-- STORED PROCEDURE
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

-- VIEW
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