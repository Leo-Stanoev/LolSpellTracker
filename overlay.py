import sys
import os
import json
import requests
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor, QScreen
import ctypes
from ctypes import wintypes
import win32gui
import win32con

# ----------------------------
# Settings persistence
# ----------------------------
BASE_DIR = os.path.join(os.getenv("APPDATA") or ".", "LoLOverlay")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
ICON_DIR = os.path.join(BASE_DIR, "icons")
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(ICON_DIR, exist_ok=True)

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except:
        pass

# ----------------------------
# Summoner spell cooldowns and icons
# ----------------------------
SUMMONER_COOLDOWNS = {
    "Flash": 300, "Teleport": 300, "Unleashed Teleport": 330, "Heal": 240,
    "Ignite": 180, "Barrier": 180, "Exhaust": 210, "Cleanse": 210, 
    "Smite": 90, "Primal Smite": 90, "Unleashed Smite": 90
}

SUMMONER_ICONS = {
    "Flash": "SummonerFlash",
    "Teleport": "SummonerTeleport",
    "Unleashed Teleport": "SummonerTeleport",
    "Heal": "SummonerHeal",
    "Ignite": "SummonerDot",
    "Barrier": "SummonerBarrier",
    "Exhaust": "SummonerExhaust",
    "Cleanse": "SummonerBoost",
    "Smite": "SummonerSmite",
    "Primal Smite": "SummonerSmitePrimal",
    "Unleashed Smite": "SummonerSmiteUnleashed",
}

def get_summoner_cd(name, level):
    if name == "Unleashed Teleport":
        cd = 330 - min(level, 10) * 10
        return max(cd, 240)
    return SUMMONER_COOLDOWNS.get(name, 180)

def get_champion_icon(champ_name):
    file_name = champ_name.capitalize() + ".png"
    path = os.path.join(ICON_DIR, file_name)
    if not os.path.exists(path):
        try:
            version = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=2).json()[0]
            url = f"http://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{file_name}"
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                with open(path, "wb") as f:
                    f.write(r.content)
        except:
            return None
    return QPixmap(path) if os.path.exists(path) else None

def get_summoner_icon(name):
    path = os.path.join(ICON_DIR, f"{name}.png")
    if not os.path.exists(path) and name in SUMMONER_ICONS:
        spell_id = SUMMONER_ICONS[name]
        url = f"https://ddragon.leagueoflegends.com/cdn/13.24.1/img/spell/{spell_id}.png"
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                with open(path, "wb") as f:
                    f.write(r.content)
        except:
            return None
    return path if os.path.exists(path) else None

# ----------------------------
# Spell button with icon + cooldown swipe
# ----------------------------
class SpellButton(QPushButton):
    def __init__(self, name, cooldown):
        super().__init__()
        self.name = name
        self.cooldown = cooldown
        self.remaining = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.icon_path = get_summoner_icon(name)
        self.setFixedSize(35, 35)
        self.setStyleSheet("border-radius:5px; background-color:#222;")
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)

        # Draw icon
        if self.icon_path:
            pix = QPixmap(self.icon_path).scaled(32,32,Qt.KeepAspectRatio,Qt.SmoothTransformation)
            painter.drawPixmap(1,1,pix)

        # Draw cooldown bar
        if self.remaining > 0:
            h = int(32 * self.remaining / self.cooldown)
            painter.fillRect(1, 33 - h, 32, h, QColor(0, 0, 0, 180))

            # Draw text with outline
            painter.setFont(QFont("Arial", 12, QFont.Bold))
            rect = self.rect()
            text = str(self.remaining)

            # Draw outline in black
            painter.setPen(Qt.black)
            offsets = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]
            for dx, dy in offsets:
                painter.drawText(rect.translated(dx, dy), Qt.AlignCenter, text)

            # Draw main text in white
            painter.setPen(Qt.white)
            painter.drawText(rect, Qt.AlignCenter, text)


    def mousePressEvent(self, event):
        if event.button()==Qt.LeftButton:
            if self.remaining<=0: self.start()
            else: self.deduct(10)
        elif event.button()==Qt.RightButton:
            self.reset()
        event.accept()

    def start(self):
        self.remaining=self.cooldown
        self.timer.start(1000)
        self.update()

    def tick(self):
        self.remaining-=1
        if self.remaining<=0: self.timer.stop()
        self.update()

    def reset(self):
        self.timer.stop()
        self.remaining=0
        self.update()

    def deduct(self, sec):
        self.remaining-=sec
        if self.remaining<=0: self.reset()
        else: self.update()

# ----------------------------
# Overlay window
# ----------------------------
class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LoL Overlay")
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setFocusPolicy(Qt.NoFocus)

        settings = load_settings()
        self.offset_x = settings.get("offset_x", 10)
        self.offset_y = settings.get("offset_y", 100)
        self.last_lol_hwnd = None
        self.last_position = settings.get("last_position", None)
        if self.last_position:
            x, y = self.last_position
            self.move(x, y)

        # Main frame
        self.main_frame = QFrame(self)
        self.main_frame.setStyleSheet("background: rgba(0,0,0,25); border-radius:5px;")
        self.main_layout = QVBoxLayout(self.main_frame)
        self.main_layout.setSpacing(5)
        self.main_layout.setContentsMargins(5,5,5,5)
        self.main_frame.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        self.layout().addWidget(self.main_frame)

        # Top bar
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        
        self.close_btn = QPushButton("X")
        self.close_btn.setFixedSize(15,15)
        self.close_btn.setFont(QFont("Arial",8,QFont.Bold))
        self.close_btn.setStyleSheet("""
            QPushButton{color:white;background:rgba(0,0,0,50);border:none;border-radius:3px;}
            QPushButton:hover{background:rgba(0,0,0,100);}
        """)
        self.close_btn.clicked.connect(lambda:(self.close(),QApplication.quit()))
        top_bar.addWidget(self.close_btn, alignment=Qt.AlignRight)
        self.main_layout.addLayout(top_bar)

        # Container for enemies
        self.enemies_container = QVBoxLayout()
        self.enemies_container.setSpacing(3)
        self.main_layout.addLayout(self.enemies_container)
        self.enemies_container.setSizeConstraint(QVBoxLayout.SetMinimumSize)

        self.player_frames = {}
        self.drag_position = None

        # Poll API
        self.api_timer = QTimer()
        self.api_timer.timeout.connect(self.poll_api)
        self.api_timer.start(1000)

        # Anchor to LoL window
        self.anchor_timer = QTimer()
        self.anchor_timer.timeout.connect(self.anchor_to_lol)
        self.anchor_timer.start(50)
        
        # Initial size adjustment
        self.adjustSize()

    def anchor_to_lol(self):
        """Anchor overlay to League of Legends window"""
        hwnd_lol = win32gui.FindWindow(None, "League of Legends (TM) Client")
        
        if hwnd_lol:
            self.last_lol_hwnd = hwnd_lol
            
            # Check if LoL is the foreground window
            foreground = win32gui.GetForegroundWindow()
            
            if foreground == hwnd_lol:
                # Show overlay when LoL is in foreground
                if not self.isVisible():
                    self.show()
                    
                rect = win32gui.GetWindowRect(hwnd_lol)
                x, y, right, bottom = rect
                
                # Position overlay relative to LoL window
                overlay_x = x + self.offset_x
                overlay_y = y + self.offset_y
                
                hwnd_overlay = self.winId().__int__()
                ctypes.windll.user32.SetWindowPos(
                    hwnd_overlay,
                    win32con.HWND_TOPMOST,
                    overlay_x, overlay_y,
                    0, 0,  # Don't change size
                    win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
                )
            else:
                # Hide overlay when LoL is not in foreground
                if self.isVisible():
                    self.hide()
        else:
            # Hide if LoL window not found
            if self.isVisible():
                self.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.drag_position:
            pos = event.globalPosition().toPoint() - self.drag_position

            screen_geom = QApplication.primaryScreen().geometry()
            w, h = self.width(), self.height()

            # Clamp X
            pos.setX(max(screen_geom.left(), min(pos.x(), screen_geom.right() - w)))
            # Clamp Y
            pos.setY(max(screen_geom.top(), min(pos.y(), screen_geom.bottom() - h)))

            self.move(pos)
            self.last_position = (pos.x(), pos.y())  # track for saving
            # Update offset relative to LoL window if it exists
            if self.last_lol_hwnd:
                try:
                    rect = win32gui.GetWindowRect(self.last_lol_hwnd)
                    self.offset_x = pos.x() - rect[0]
                    self.offset_y = pos.y() - rect[1]
                except:
                    pass

    def mouseReleaseEvent(self, event):
        self.drag_position = None

    def poll_api(self):
        url = "https://127.0.0.1:2999/liveclientdata/allgamedata"
        try:
            r = requests.get(url, verify=False, timeout=1)
            if r.status_code != 200: return
            data = r.json()
            players = data.get("allPlayers", [])
            active_name = data.get("activePlayer", {}).get("summonerName", "")
            my_team = next((p.get("team") for p in players if p.get("summonerName") == active_name), "")

            for p in players:
                pid = p.get("summonerName")
                team = p.get("team")
                if pid == active_name or team == my_team: continue
                lvl = p.get("level",1)

                if pid not in self.player_frames:
                    row_widget = QWidget()
                    row_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                    row_layout = QHBoxLayout(row_widget)
                    row_layout.setContentsMargins(0,0,0,0)
                    row_layout.setSpacing(0)

                    buttons = []

                    champ_pix = get_champion_icon(p.get("championName",""))
                    if champ_pix:
                        lbl_icon = QLabel()
                        lbl_icon.setPixmap(champ_pix.scaled(35,35,Qt.KeepAspectRatio,Qt.SmoothTransformation))
                        lbl_icon.setFixedSize(35,35)
                        lbl_icon.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
                        row_layout.addWidget(lbl_icon)
                        row_layout.addSpacing(5)

                    for i,key in enumerate(["summonerSpellOne","summonerSpellTwo"]):
                        spell = p.get("summonerSpells",{}).get(key)
                        if spell:
                            name = spell.get("displayName","Spell")
                            cd = p.get("summonerSpellCooldowns",{}).get(key,get_summoner_cd(name,lvl))
                            btn = SpellButton(name,cd)
                            btn.setFixedSize(35,35)
                            btn.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
                            row_layout.addWidget(btn)
                            buttons.append(btn)
                            if i==0: row_layout.addSpacing(2)

                    self.enemies_container.addWidget(row_widget, alignment=Qt.AlignLeft)
                    self.player_frames[pid]=buttons

                else:
                    buttons = self.player_frames[pid]
                    for i,key in enumerate(["summonerSpellOne","summonerSpellTwo"]):
                        spell = p.get("summonerSpells",{}).get(key)
                        if spell and i<len(buttons):
                            cd = p.get("summonerSpellCooldowns",{}).get(key,get_summoner_cd(spell["displayName"],lvl))
                            btn = buttons[i]
                            if btn.remaining<=0:
                                btn.cooldown=cd
                                btn.update()

            self.adjustSize()

        except:
            pass

    def closeEvent(self,event):
        save_settings({
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "last_position": (self.x(), self.y())
        })
        super().closeEvent(event)

if __name__=="__main__":
    import warnings
    warnings.filterwarnings("ignore")
    app = QApplication(sys.argv)
    overlay = Overlay()
    overlay.show()
    sys.exit(app.exec())