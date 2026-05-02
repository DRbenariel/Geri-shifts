import hashlib
import gspread
import json

# --- Configuration ---
SERVICE_ACCOUNT_FILE = "gerishifts-7ccae6b773f7.json"
SPREADSHEET_URL = None  # Will be read from .streamlit/secrets.toml

def get_spreadsheet_url():
    """Read the spreadsheet URL from Streamlit secrets."""
    import toml
    secrets = toml.load(".streamlit/secrets.toml")
    return secrets["connections"]["gsheets"]["spreadsheet"]

def reset_admin_password(new_password="1234"):
    """Reset the admin password in Google Sheets to the given value."""
    new_hash = hashlib.sha256(new_password.encode()).hexdigest()
    
    try:
        # Connect to Google Sheets
        gc = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)
        url = get_spreadsheet_url()
        sh = gc.open_by_url(url)
        ws = sh.worksheet("staff")
        
        # Get all records
        records = ws.get_all_records()
        
        # Find admin rows and update
        updated = 0
        for i, row in enumerate(records):
            if row.get('type') == 'מנהל/ת':
                # Row index in sheet is i+2 (1-indexed header + 1-indexed data)
                # Find the password column
                headers = ws.row_values(1)
                pass_col = headers.index('password') + 1  # 1-indexed
                ws.update_cell(i + 2, pass_col, new_hash)
                updated += 1
                print(f"  Reset password for: {row.get('name', 'Unknown')}")
        
        if updated > 0:
            print(f"\nSuccessfully reset password for {updated} admin user(s) to '{new_password}'.")
        else:
            print("No admin users found in the staff sheet.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Resetting admin password...")
    reset_admin_password("1234")
