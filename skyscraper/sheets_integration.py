"""
Google Sheets integration module for saving scraped data
"""
import logging
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build

from config import GOOGLE_SHEETS_CONFIG

logger = logging.getLogger(__name__)


class GoogleSheetsManager:
    """Manage Google Sheets integration"""

    def __init__(self):
        """Initialize Google Sheets manager"""
        self.credentials = None
        self.service = None
        self.spreadsheet_id = None
        self._authenticate()

    def _authenticate(self):
        """
        Authenticate with Google Sheets API
        Supports both service account and OAuth2 authentication
        """
        credentials_file = Path(GOOGLE_SHEETS_CONFIG["credentials_file"])
        token_file = Path(GOOGLE_SHEETS_CONFIG["token_file"])

        try:
            # Try service account authentication first
            if credentials_file.exists():
                logger.info("Using service account authentication")
                self.credentials = service_account.Credentials.from_service_account_file(
                    credentials_file,
                    scopes=GOOGLE_SHEETS_CONFIG["scopes"]
                )
            # Fall back to OAuth2
            elif token_file.exists():
                logger.info("Using OAuth2 token")
                self.credentials = Credentials.from_authorized_user_file(
                    token_file,
                    GOOGLE_SHEETS_CONFIG["scopes"]
                )
            else:
                # Create new OAuth2 authentication
                logger.info("Starting OAuth2 authentication flow")
                self._oauth2_auth()

            # Build the service
            self.service = build(
                'sheets', 'v4',
                credentials=self.credentials,
                cache_discovery=False
            )
            logger.info("Successfully authenticated with Google Sheets API")

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise

    def _oauth2_auth(self):
        """
        Perform OAuth2 authentication flow
        """
        flow = InstalledAppFlow.from_client_secrets_file(
            str(GOOGLE_SHEETS_CONFIG["credentials_file"]),
            GOOGLE_SHEETS_CONFIG["scopes"]
        )

        self.credentials = flow.run_local_server(port=0)

        # Save token for future use
        token_file = Path(GOOGLE_SHEETS_CONFIG["token_file"])
        with open(token_file, 'w') as token:
            token.write(self.credentials.to_json())

        logger.info(f"OAuth2 token saved to {token_file}")

    def create_sheet(self, title):
        """
        Create a new spreadsheet

        Args:
            title: Title of the spreadsheet

        Returns:
            Spreadsheet ID
        """
        try:
            spreadsheet_body = {
                'properties': {
                    'title': title
                }
            }

            spreadsheet = self.service.spreadsheets().create(
                body=spreadsheet_body
            ).execute()

            self.spreadsheet_id = spreadsheet.get('spreadsheetId')
            logger.info(f"Created spreadsheet: {self.spreadsheet_id}")
            return self.spreadsheet_id

        except Exception as e:
            logger.error(f"Failed to create spreadsheet: {e}")
            raise

    def set_spreadsheet_id(self, spreadsheet_id):
        """Set the spreadsheet ID to work with"""
        self.spreadsheet_id = spreadsheet_id
        logger.info(f"Set spreadsheet ID: {spreadsheet_id}")

    def get_headers(self, range_name='Sheet1!A1:Z1'):
        """
        Get headers from the sheet

        Args:
            range_name: Range to read

        Returns:
            List of headers
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()

            rows = result.get('values', [])
            return rows[0] if rows else []

        except Exception as e:
            logger.error(f"Failed to get headers: {e}")
            return []

    def get_all_data(self, range_name='Sheet1'):
        """
        Get all data from the sheet

        Args:
            range_name: Range to read

        Returns:
            List of rows
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()

            return result.get('values', [])

        except Exception as e:
            logger.error(f"Failed to get sheet data: {e}")
            return []

    def append_rows(self, values, range_name='Sheet1!A1'):
        """
        Append rows to the sheet

        Args:
            values: List of rows to append
            range_name: Starting range for append

        Returns:
            Update result
        """
        try:
            body = {
                'values': values
            }

            result = self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()

            logger.info(f"Appended {len(values)} rows to sheet")
            return result

        except Exception as e:
            logger.error(f"Failed to append rows: {e}")
            raise

    def update_rows(self, values, range_name='Sheet1!A1'):
        """
        Update rows in the sheet

        Args:
            values: List of rows to update
            range_name: Starting range for update

        Returns:
            Update result
        """
        try:
            body = {
                'values': values
            }

            result = self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()

            logger.info(f"Updated {len(values)} rows in sheet")
            return result

        except Exception as e:
            logger.error(f"Failed to update rows: {e}")
            raise

    def clear_range(self, range_name='Sheet1'):
        """
        Clear a range in the sheet

        Args:
            range_name: Range to clear

        Returns:
            Clear result
        """
        try:
            result = self.service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()

            logger.info(f"Cleared range: {range_name}")
            return result

        except Exception as e:
            logger.error(f"Failed to clear range: {e}")
            raise

    def format_header(self, range_name='Sheet1!A1:Z1'):
        """
        Format header row (bold and background color)

        Args:
            range_name: Range to format
        """
        try:
            requests = [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {
                                    "bold": True,
                                    "fontSize": 12,
                                },
                                "backgroundColor": {
                                    "red": 0.2,
                                    "green": 0.2,
                                    "blue": 0.2,
                                    "alpha": 1,
                                },
                                "textFormat": {
                                    "foregroundColor": {
                                        "red": 1,
                                        "green": 1,
                                        "blue": 1,
                                        "alpha": 1,
                                    }
                                }
                            }
                        },
                        "fields": "userEnteredFormat"
                    }
                }
            ]

            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": requests}
            ).execute()

            logger.info("Formatted header row")

        except Exception as e:
            logger.warning(f"Failed to format header: {e}")


if __name__ == "__main__":
    # Test authentication
    try:
        manager = GoogleSheetsManager()
        print("Successfully authenticated with Google Sheets API")
    except Exception as e:
        print(f"Authentication failed: {e}")
