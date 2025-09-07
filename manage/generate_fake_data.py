#!/usr/bin/env python3
"""
Fake Data Generator Script
Generates 30 fake personnel records for each station using Filipino localization.
"""
import sys
import random
from datetime import datetime, timedelta, date
from faker import Faker
from werkzeug.security import generate_password_hash
from config import (
    get_app_context,
    db,
    User,
    Personnel,
    Attendance,
    FaceData,
    ActivityLog,
    StationType,
    AttendanceStatus,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_header,
    confirm_action,
)

# Initialize Faker with Philippine locale
fake = Faker("fil_PH")  # Filipino Philippines locale

# BFP Ranks in hierarchical order
BFP_RANKS = [
    "Fire Officer I",
    "Fire Officer II",
    "Fire Officer III",
    "Senior Fire Officer I",
    "Senior Fire Officer II",
    "Senior Fire Officer III",
    "Senior Fire Officer IV",
    "Chief Fire Officer",
    "Fire Chief",
]


def create_station_users():
    """Create user accounts for each station (if they don't exist)"""
    stations_created = 0

    for station_type in StationType:
        # Check if station user already exists
        existing_user = User.query.filter_by(
            station_type=station_type, is_admin=False
        ).first()

        if not existing_user:
            username = f"{station_type.value.lower()}_station"
            email = f"{station_type.value.lower()}@bfp-sorsogon.gov.ph"

            user = User(
                username=username,
                email=email,
                password=generate_password_hash("station123"),  # Default password
                station_type=station_type,
                is_admin=False,
                date_created=datetime.utcnow(),
            )

            db.session.add(user)
            stations_created += 1
            print_success(f"Created station user: {username}")

    if stations_created > 0:
        db.session.commit()
        print_success(f"Created {stations_created} station user(s)")
    else:
        print_info("All station users already exist")


def generate_personnel_for_station(station_user, count=30):
    """Generate fake personnel for a specific station"""
    personnel_created = []

    print_info(f"Generating {count} personnel for {station_user.station_name}...")

    for i in range(count):
        # Generate Filipino name
        first_name = fake.first_name()
        last_name = fake.last_name()

        # Assign random rank (weighted towards lower ranks)
        rank_weights = [30, 25, 20, 15, 10, 8, 5, 3, 1]  # More junior personnel
        rank = random.choices(BFP_RANKS, weights=rank_weights)[0]

        # Create personnel record
        personnel = Personnel(
            first_name=first_name,
            last_name=last_name,
            rank=rank,
            station_id=station_user.id,
            date_created=fake.date_time_between(start_date="-2y", end_date="now"),
        )

        db.session.add(personnel)
        personnel_created.append(personnel)

    # Flush to get IDs for the personnel
    db.session.flush()

    print_success(
        f"Created {len(personnel_created)} personnel for {station_user.station_name}"
    )
    return personnel_created


def generate_attendance_history(personnel_list, days_back=90):
    """Generate realistic attendance history for personnel"""
    print_info(f"Generating attendance history for {len(personnel_list)} personnel...")

    attendance_created = 0
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)

    for personnel in personnel_list:
        current_date = start_date

        while current_date <= end_date:
            # Skip weekends (Saturday=5, Sunday=6)
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            # 85% chance of attendance on any given day
            if random.random() < 0.85:
                # Generate realistic time_in (7:00 AM to 9:00 AM)
                time_in_hour = random.randint(7, 8)
                time_in_minute = random.randint(0, 59)
                time_in = datetime.combine(
                    current_date,
                    datetime.min.time().replace(
                        hour=time_in_hour, minute=time_in_minute
                    ),
                )

                # Generate time_out (4:00 PM to 6:00 PM) with 90% probability
                time_out = None
                if random.random() < 0.90:
                    time_out_hour = random.randint(16, 17)
                    time_out_minute = random.randint(0, 59)
                    time_out = datetime.combine(
                        current_date,
                        datetime.min.time().replace(
                            hour=time_out_hour, minute=time_out_minute
                        ),
                    )

                # Determine status
                if time_in_hour >= 8:
                    status = AttendanceStatus.LATE
                else:
                    status = AttendanceStatus.PRESENT

                attendance = Attendance(
                    personnel_id=personnel.id,
                    date=current_date,
                    time_in=time_in,
                    time_out=time_out,
                    status=status,
                    confidence_score=random.uniform(0.85, 0.98),
                    is_auto_captured=True,
                    is_approved=True,
                    date_created=time_in,
                )

                db.session.add(attendance)
                attendance_created += 1

            current_date += timedelta(days=1)

    print_success(f"Created {attendance_created} attendance records")


def generate_fake_face_data(personnel_list):
    """Generate fake face data entries for personnel"""
    print_info(f"Generating face data for {len(personnel_list)} personnel...")

    face_data_created = 0

    for personnel in personnel_list:
        # Each personnel gets 2-4 face encodings
        num_faces = random.randint(2, 4)

        for i in range(num_faces):
            face_data = FaceData(
                personnel_id=personnel.id,
                filename=f"face_{personnel.id}_{i+1}.jpg",
                embedding="[fake_embedding_data]",  # Placeholder for actual face encoding
                confidence=random.uniform(0.80, 0.95),
                date_created=fake.date_time_between(
                    start_date=personnel.date_created, end_date="now"
                ),
            )

            db.session.add(face_data)
            face_data_created += 1

    print_success(f"Created {face_data_created} face data records")


def generate_activity_logs(station_users):
    """Generate activity logs for station users"""
    print_info("Generating activity logs...")

    activities = [
        "Personnel Added",
        "Personnel Updated",
        "Attendance Approved",
        "Face Registration Completed",
        "System Login",
        "Report Generated",
        "Database Backup Created",
    ]

    logs_created = 0

    for user in station_users:
        # Generate 10-20 activity logs per user
        num_logs = random.randint(10, 20)

        for _ in range(num_logs):
            activity = random.choice(activities)

            activity_log = ActivityLog(
                user_id=user.id,
                title=activity,
                description=f"{activity} - {fake.sentence()}",
                timestamp=fake.date_time_between(start_date="-30d", end_date="now"),
            )

            db.session.add(activity_log)
            logs_created += 1

    print_success(f"Created {logs_created} activity log records")


def generate_all_fake_data(personnel_per_station=30):
    """Generate complete fake dataset"""
    try:
        with get_app_context():
            print_header("GENERATING FAKE DATA FOR BFP ATTENDANCE SYSTEM")

            # Check if data already exists
            existing_personnel = Personnel.query.count()
            if existing_personnel > 0:
                if not confirm_action(
                    f"Database already contains {existing_personnel} personnel. Continue adding more?"
                ):
                    print_warning("Operation cancelled.")
                    return False

            print_info(f"Generating {personnel_per_station} personnel per station...")
            print_info("This may take a few minutes...")

            # Step 1: Create station users
            print_info("\n1. Creating station users...")
            create_station_users()

            # Step 2: Get all non-admin station users
            station_users = User.query.filter_by(is_admin=False).all()
            if not station_users:
                print_error(
                    "No station users found! Please create station users first."
                )
                return False

            print_info(
                f"Found {len(station_users)} station(s): {[u.station_name for u in station_users]}"
            )

            # Step 3: Generate personnel for each station
            print_info("\n2. Generating personnel...")
            all_personnel = []
            for station_user in station_users:
                personnel = generate_personnel_for_station(
                    station_user, personnel_per_station
                )
                all_personnel.extend(personnel)

            # Commit personnel data
            db.session.commit()
            print_success(f"Created total of {len(all_personnel)} personnel")

            # Step 4: Generate face data
            print_info("\n3. Generating face data...")
            generate_fake_face_data(all_personnel)

            # Step 5: Generate attendance history
            print_info("\n4. Generating attendance history...")
            generate_attendance_history(all_personnel, days_back=90)

            # Step 6: Generate activity logs
            print_info("\n5. Generating activity logs...")
            generate_activity_logs(station_users)

            # Final commit
            db.session.commit()

            # Show summary
            print_header("FAKE DATA GENERATION COMPLETED")
            print_success("Database has been populated with fake data!")

            print_info("Summary:")
            print(f"  Stations: {User.query.filter_by(is_admin=False).count()}")
            print(f"  Personnel: {Personnel.query.count()}")
            print(f"  Attendance Records: {Attendance.query.count()}")
            print(f"  Face Data: {FaceData.query.count()}")
            print(f"  Activity Logs: {ActivityLog.query.count()}")

            return True

    except Exception as e:
        print_error(f"Error generating fake data: {str(e)}")
        try:
            db.session.rollback()
        except:
            pass
        return False


def main():
    """Main function"""
    print_header("BFP ATTENDANCE SYSTEM - FAKE DATA GENERATOR")

    print("This script will generate fake data for development/testing.")
    print("Using Filipino locale for realistic Philippine names.")
    print("\nData to be generated:")
    print("  • 30 personnel per station (120 total)")
    print("  • 90 days of attendance history")
    print("  • Face data entries")
    print("  • Activity logs")

    print("\nOptions:")
    print("1. Generate standard dataset (30 personnel per station)")
    print("2. Generate custom dataset (specify count)")
    print("3. Show current data counts")
    print("4. Cancel")

    try:
        choice = input("\nEnter your choice (1-4): ").strip()

        if choice == "1":
            generate_all_fake_data(30)
        elif choice == "2":
            try:
                count = int(input("Enter number of personnel per station (1-100): "))
                if 1 <= count <= 100:
                    generate_all_fake_data(count)
                else:
                    print_error("Count must be between 1 and 100.")
            except ValueError:
                print_error("Invalid number entered.")
        elif choice == "3":
            with get_app_context():
                print_info("Current database status:")
                print(f"  Users: {User.query.count()}")
                print(f"  Personnel: {Personnel.query.count()}")
                print(f"  Attendance: {Attendance.query.count()}")
                print(f"  Face Data: {FaceData.query.count()}")
                print(f"  Activity Logs: {ActivityLog.query.count()}")
        elif choice == "4":
            print_warning("Operation cancelled.")
        else:
            print_error("Invalid choice. Operation cancelled.")

    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user.")
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    main()
