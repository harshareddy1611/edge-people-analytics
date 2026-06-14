import sys
sys.path.insert(0, '/home/vision/projects/people-analytics')

from shared.config import AD_CATEGORIES, AD_WINDOW_SECS
from shared.database import get_demographics_last_minutes, log_ad_selection
from datetime import datetime


class AdSelector:
    def __init__(self):
        self.current_ad     = "default"
        self.last_update    = datetime.now()
        self.update_interval = AD_WINDOW_SECS

    def get_dominant_demographic(self):
        """Look at last 30 seconds of face events and find majority."""
        rows = get_demographics_last_minutes(minutes=1)

        if not rows:
            return None, None, 0

        # Find dominant combination
        best       = max(rows, key=lambda x: x['count'])
        gender     = best['gender']
        age_group  = best['age_group']
        count      = best['count']

        return gender, age_group, count

    def select_ad(self, person_count=0):
        """Select ad category based on current demographics."""
        now = datetime.now()
        elapsed = (now - self.last_update).seconds

        if elapsed < self.update_interval:
            return self.current_ad

        gender, age_group, count = self.get_dominant_demographic()

        if gender is None or age_group is None:
            return self.current_ad

        # Map age group from model output to config keys
        age_key = self._map_age_group(age_group)

        # Look up ad category
        ad = AD_CATEGORIES.get((age_key, gender), "default")

        if ad != self.current_ad:
            print(f"[AdSelector] Switching ad: {self.current_ad} → {ad}")
            print(f"             Dominant: {gender}, {age_group} (seen {count}x)")
            log_ad_selection(ad, age_group, gender, person_count)
            self.current_ad = ad

        self.last_update = now
        return self.current_ad

    def _map_age_group(self, model_age):
        """Map Caffe model age ranges to our config age groups."""
        mapping = {
            '0-2':    '0-17',
            '4-6':    '0-17',
            '8-12':   '0-17',
            '15-20':  '0-17',
            '25-32':  '18-28',
            '38-43':  '29-45',
            '48-53':  '46+',
            '60-100': '46+',
        }
        return mapping.get(model_age, '18-28')


if __name__ == "__main__":
    selector = AdSelector()
    ad = selector.select_ad(person_count=3)
    print(f"Current ad: {ad}")
