# Pellet – Uruchamianie i harmonogram

Ten plik opisuje, jak uruchomić skrypt oraz jak ustawić codzienne wykonywanie w Windows.

## Wymagania
- Windows 10/11
- Python 3.11+ zainstalowany
- Dostęp do Internetu (skrypt pobiera strony produktów)

## Instalacja zależności
W katalogu projektu:

```powershell
python -m pip install -r requirements.txt
```

Jeśli nie masz `requirements.txt`, zainstaluj bezpośrednio:

```powershell
python -m pip install requests beautifulsoup4 lxml playwright
```

## Uruchomienie ręczne
W katalogu projektu:

```powershell
python .\pellet-tracker.py
```

Pliki wyjściowe:
- `pellet_prices.jsonl` (historia)
- `pellet_prices_latest.json` (ostatni snapshot)
- `pellet_prices.csv`
- `runs.txt` (logi uruchomień)

## Harmonogram dzienny (Task Scheduler)
Uruchom poniższe polecenia w **Wierszu poleceń** (nie w PowerShell), jako swoje konto:

```cmd
schtasks /create /sc daily /st 13:00 /tn "Pellet prices - daily scrape" ^
  /tr "cmd /c cd /d \"C:\Users\USER\Documents\Pellet\" && \"C:\Users\USER\AppData\Local\Microsoft\WindowsApps\python3.13.exe\" \"pellet-tracker.py\"" ^
  /rl highest
```

Dlaczego tak:
- `cd /d` ustawia katalog roboczy, więc pliki zapisują się w projekcie.
- `python3.13.exe` uruchamia skrypt we właściwym interpreterze.

## Weryfikacja harmonogramu
Sprawdź status:

```cmd
schtasks /query /tn "Pellet prices - daily scrape" /v /fo LIST
```

Potwierdź, że pliki zostały zaktualizowane:
- Sprawdź datę modyfikacji `pellet_prices_latest.json` i `runs.txt`.

## Opcjonalnie: uruchamianie po wylogowaniu
Aby uruchamiać zadanie bez zalogowanego użytkownika, utwórz zadanie z podanym kontem i hasłem (wartości domyślne):

```cmd
schtasks /create /sc daily /st 13:00 /tn "Pellet prices - daily scrape" ^
  /tr "cmd /c cd /d \"C:\Users\USER\Documents\Pellet\" && \"C:\Users\USER\AppData\Local\Microsoft\WindowsApps\python3.13.exe\" \"pellet-tracker.py\"" ^
  /ru "MACHINE_NAME\USER" /rp YOUR_PASSWORD /rl highest
```

Uwagi:
- Zastąp `YOUR_PASSWORD` swoim hasłem Windows lub usuń fragment polecenia `/rp YOUR_PASSWORD /rl highest` (niezalecane).
- Zastąp `USER` i `MACHINE_NAME` aktualną nazwą użytkownika i komputera.
- Przy zmianie wersji Pythona zaktualizuj ścieżkę do `python3.13.exe`.
