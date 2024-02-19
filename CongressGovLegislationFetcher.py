import threading
from tqdm import tqdm
import requests
from dotenv import load_dotenv
import os
import re

load_dotenv()

class CongressGovLegislationFetcher:
    def __init__(self, api_key, congress):
        self.api_key = api_key
        self.congress = congress
        self.base_url = "https://api.congress.gov/v3/bill"
        self.data_lock = threading.Lock()
        self.condition = threading.Condition(self.data_lock)
        self.bills = []
        self.is_fetching = False
        self.page = 0
        self.finished = False
        self.limit = 10  # Adjust based on API limits

    @staticmethod
    def calculate_congress_date_range(congress):
        """
        Calculate the start and end dates for the specified Congress.
        Each Congress lasts for two years, starting on January 3rd of odd-numbered years.
        """
        # Congresses start on January 3rd of odd-numbered years and last for two years.
        start_year = 1789 + (int(congress) - 1) * 2
        end_year = start_year + 2  # The year after the Congress ends
        from_date = f"{start_year}-01-03T00:00:00Z"
        to_date = f"{end_year}-01-03T00:00:00Z"  # Include actions up to the end of the Congress period
        return from_date, to_date

    def fetch_bills(self):
        while not self.finished:
            with self.condition:
                if self.is_fetching:
                    return
                self.is_fetching = True

            from_date, to_date = self.calculate_congress_date_range(congress)
            offset = self.page * self.limit
            url = f"{self.base_url}/{self.congress}?fromDateTime={from_date}&toDateTime={to_date}&sort=updateDate+desc&limit={self.limit}&offset={offset}&api_key={self.api_key}"

            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()
                bills_data = data.get('bills', [])

                with self.condition:
                    if bills_data:
                        self.bills.extend(bills_data)
                        self.page += 1  # Prepare for the next page
                        if len(bills_data) < self.limit:
                            self.finished = True  # Last page
                    else:
                        self.finished = True

            except requests.exceptions.RequestException as e:
                with self.condition:
                    print(f"Failed to fetch data: {e}")
                    self.finished = True

            finally:
                with self.condition:
                    self.is_fetching = False
                    self.condition.notify_all()

            if self.finished:
                break

    def next_bill(self):
        with self.condition:
            while not self.bills and not self.finished:
                if not self.is_fetching:
                    threading.Thread(target=self.fetch_bills, daemon=True).start()
                self.condition.wait()

            if self.bills:
                return self.bills.pop(0)
            return None

def run_test(congress, api_key, num_threads=5, num_items=1):
    bills = []
    fetcher = CongressGovLegislationFetcher(api_key=api_key, congress=congress)

    def process_bill(progress):
        while progress.n < progress.total:
            bill = fetcher.next_bill()
            if bill:
                progress.update(1)
                print(f"Fetched bill: S{bill['number']} - {bill['title']} - {bill['url']}")
                bills.append(bill)
            else:
                # Exit the loop if no more bills to fetch
                break

    with tqdm(total=num_items, desc="Fetching bills", unit="bill") as progress:
        threads = [threading.Thread(target=process_bill, args=(progress,), daemon=True) for _ in range(num_threads)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

def get_bill_text(congress, bill_number):
    print("Getting bill text")
    # Construct the URL for the bill
    url = f"https://www.congress.gov/{congress}/bills/s{bill_number}/BILLS-{congress}s{bill_number}is.htm"
    print(url)
    
    # Send a request to the URL and get the response
    response = requests.get(url)
    
    # Check if the request was successful (status code 200)
    if response.status_code == 200:
        return response.text
    else:
        # If the request was not successful, return None
        return None


if __name__ == "__main__":
    api_key = os.getenv('CONGRESSGOV_API_KEY')
    if not api_key:
        raise EnvironmentError("CONGRESSGOV_API_KEY environment variable not set.")
    congress = "117"
    run_test(congress, api_key)
