import unittest
import re
from datetime import datetime

class TestRecipeLogic(unittest.TestCase):
    """
    Test suite for Recipe parsing, scaling, and helper methods.
    """

    def test_parsed_ingredients_scaling(self):
        units_set = {'г', 'гр', 'кг', 'мл', 'л', 'ч.л.', 'ч. л.', 'ст.л.', 'ст. л.', 'шт', 'шт.', 'зубчик', 'щепотка'}
        test_ingredients = """400 г спагетти
150 г гуанчале
4 шт. яичных желтка
Соль по вкусу
2.5 ст. л. оливкового масла"""

        results = []
        for line in test_ingredients.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            m = re.match(r'^\s*(?:[-*•]\s*)?([\d.,]+)\s*([a-zA-Zа-яА-ЯёЁ.]+)?\s*(.*)$', line)
            if m:
                raw_amt, potential_unit, rest = m.groups()
                try:
                    amt = float(raw_amt.replace(',', '.'))
                except ValueError:
                    amt = None
                potential_unit = (potential_unit or '').strip().lower()
                rest = (rest or '').strip()

                if potential_unit in units_set:
                    unit = potential_unit
                    name = rest
                else:
                    unit = ''
                    name = f"{potential_unit} {rest}".strip()

                results.append({'raw': line, 'amount': amt, 'unit': unit, 'name': name})
            else:
                results.append({'raw': line, 'amount': None, 'unit': '', 'name': line})

        self.assertEqual(len(results), 5)
        self.assertEqual(results[0]['amount'], 400.0)
        self.assertEqual(results[0]['unit'], 'г')
        self.assertEqual(results[0]['name'], 'спагетти')

        self.assertEqual(results[2]['amount'], 4.0)
        self.assertEqual(results[2]['unit'], 'шт.')

        self.assertIsNone(results[3]['amount'])
        self.assertEqual(results[3]['name'], 'Соль по вкусу')

        self.assertEqual(results[4]['amount'], 2.5)

    def test_timer_detection_in_instructions(self):
        test_instructions = """1. Нарежьте бекон кусочками и обжарьте на среднем огне 7-8 минут до хруста.
2. В отдельной миске взбейте яйца с сыром.
3. Варите пасту в кипящей воде ровно 9 минут до аль денте.
4. Выпекайте пирог в духовке 1 час до золотистой корочки."""

        timer_pattern = re.compile(r'(\d+)\s*(?:-|–|\s+до\s+)?(\d+)?\s*(минут|мин|минуты|минута|секунд|сек|часов|часа|час)', re.IGNORECASE)
        steps = []
        for line in test_instructions.split('\n'):
            m = timer_pattern.search(line)
            detected_seconds = 0
            if m:
                val1 = int(m.group(1))
                val2 = int(m.group(2)) if m.group(2) else val1
                unit = m.group(3).lower()
                avg_val = (val1 + val2) // 2
                if 'час' in unit:
                    detected_seconds = avg_val * 3600
                elif 'мин' in unit:
                    detected_seconds = avg_val * 60
                elif 'сек' in unit:
                    detected_seconds = avg_val
            steps.append((line, detected_seconds, m.group(0) if m else None))

        self.assertEqual(steps[0][1], 7 * 60) # 7-8 mins
        self.assertEqual(steps[1][1], 0)      # No timer
        self.assertEqual(steps[2][1], 9 * 60) # 9 mins
        self.assertEqual(steps[3][1], 3600)   # 1 hour

    def test_total_time_formatting(self):
        def format_time(prep, cook):
            total = prep + cook
            if total < 60:
                return f"{total} мин"
            hours = total // 60
            rem = total % 60
            if rem == 0:
                return f"{hours} ч"
            return f"{hours} ч {rem} мин"

        self.assertEqual(format_time(10, 15), "25 мин")
        self.assertEqual(format_time(15, 45), "1 ч")
        self.assertEqual(format_time(30, 90), "2 ч")
        self.assertEqual(format_time(15, 60), "1 ч 15 мин")

if __name__ == '__main__':
    unittest.main()
