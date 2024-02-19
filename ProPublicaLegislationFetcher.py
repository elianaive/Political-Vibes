import os
import requests
import threading
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

class ProPublicaLegislationFetcher:
    def __init__(self, api_key, congress):
        self.api_key = api_key
        self.congress = congress  # Specific Congress number
        self.base_url = "https://api.propublica.org/congress/v1"
        self.headers = {"X-API-Key": api_key}
        self.data_lock = threading.Lock()
        self.bills = []
        self.is_fetching = False
        self.page = 0  # Track current page for pagination
        self.finished = False  # Indicates if all pages have been fetched

    def fetch_bills(self):
        if self.finished:
            return  # No more data to fetch

        with self.data_lock:
            if self.is_fetching:
                return
            self.is_fetching = True
            # Adjust for pagination offset
            offset = self.page * 20  # Assuming 20 items per page

        try:
            print("sending request")
            # Correct URL with chamber and type of bills (introduced)
            url = f"{self.base_url}/{self.congress}/both/bills/introduced.json?offset={offset}"
            print(url)
            response = requests.get(url, headers=self.headers, timeout=10)
            print(response.text)
            response.raise_for_status()

            with self.data_lock:
                data = response.json()
                if not data['results'][0]['bills']:
                    self.finished = True
                self.bills.extend(data['results'][0]['bills'])
                if len(data['results'][0]['bills']) < 20:
                    self.finished = True  # Assuming less than 20 bills means we've hit the last page
        except requests.exceptions.RequestException as e:
            with self.data_lock:
                print(f"Failed to fetch data: {e}")
                if self.page > 0:
                    self.page -= 1  # Only revert if we're not on the first page
        finally:
            with self.data_lock:
                self.is_fetching = False


    def next_bill(self):
        print("next bill")
        while True:
            with self.data_lock:
                print("locked")
                if not self.bills and not self.is_fetching and not self.finished:
                    print ("fetch bills")
                    self.fetch_bills()
                    continue
                if self.bills:
                    print("pop")
                    return self.bills.pop(0)
                if self.finished:
                    return None

def run_test(congress, api_key, num_threads=5, num_items=10):
    fetcher = ProPublicaLegislationFetcher(api_key=api_key, congress=congress)

    def process_bill(progress):
        bill = fetcher.next_bill()
        print(bill)
        if bill:
            progress.update(1)
            print(f"Fetched bill: {bill['bill_id']} - {bill['title']}")

    with tqdm(total=num_items, desc=f"Fetching bills from the {congress}th Congress", unit="bill") as progress:
        threads = [threading.Thread(target=lambda: process_bill(progress)) for _ in range(num_threads)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

if __name__ == "__main__":
    api_key = os.getenv('PROPUBLICA_API_KEY')
    print(f"API Key: {api_key}")
    if not api_key:
        raise EnvironmentError("PROPUBLICA_API_KEY environment variable not set.")
    congress = "117"
    fetcher = ProPublicaLegislationFetcher(api_key, congress)
    fetcher.fetch_bills()  # Test direct call
    run_test(congress, api_key)
