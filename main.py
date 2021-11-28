from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
)
from telegram import Update, ReplyKeyboardMarkup
import requests
import re
import json
import websocket
from threading import Thread, Event
import time
import os
from dotenv import load_dotenv

load_dotenv()


class WioSensor:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.token = token

    def postData(self, url):
        contents = requests.post(url).json()
        return contents

    def getData(self, url):
        contents = requests.get(url).json()
        return contents


class WioRelay(WioSensor):
    def __init__(self, base_url, token):
        WioSensor.__init__(self, base_url, token)

    def getStatus(self):
        url = self.base_url + "/onoff_status?access_token=" + self.token
        return self.getData(url)

    def setOn(self):
        url = self.base_url + "/onoff/1?access_token=" + self.token
        return self.postData(url)

    def setOff(self):
        url = self.base_url + "/onoff/0?access_token=" + self.token
        return self.postData(url)

    def getStatusCallback(self, update: Update, context: CallbackContext):
        contents = self.getStatus()
        update.message.reply_text(json.dumps(contents))

    def setOnCallback(self, update: Update, context: CallbackContext):
        contents = self.setOn()
        update.message.reply_text(json.dumps(contents))

    def setOffCallback(self, update: Update, context: CallbackContext):
        contents = self.setOff()
        update.message.reply_text(json.dumps(contents))


class WioTemp(WioSensor):
    def __init__(self, base_url, token):
        WioSensor.__init__(self, base_url, token)

    def getTemp(self):
        url = self.base_url + "/temp?access_token=" + self.token
        return self.getData(url)

    def getTempCallback(self, update: Update, context: CallbackContext):
        contents = self.getTemp()
        update.message.reply_text(
            "Hiện tại nhiệt độ là " + str(contents["temperature"]) + " độ"
        )


class WioPIR(WioSensor):
    def __init__(self, base_url, token):
        WioSensor.__init__(self, base_url, token)
        self.warn_id_list = {}
        self.ws_thread = Thread(target=self.initWebsocket)
        self.ws_thread.start()
        self.event = Event()
        self.action_thread = Thread(target=self.actionThread)
        self.action_thread.start()
        self.actionFunc = None
        self.actionEndFunc = None

    def initWebsocket(self):
        self.ws = websocket.WebSocketApp(
            "wss://us.wio.seeed.io/v1/node/event",
            on_open=self.socOnOpen,
            on_message=self.socOnMessage,
        )
        self.ws.run_forever()

    def socOnOpen(self, ws):
        self.ws.send(self.token)

    def socOnMessage(self, ws, message):
        print("kich hoat")
        for id in self.warn_id_list:
            self.warn_id_list[id].bot.send_message(
                id, "BÁO ĐỘNG: có gì đó kích hoạt PIR"
            )
        if self.actionFunc is not None:
            print("vo action")
            self.actionFunc()
            self.event.set()

    def actionThread(self):
        while 1:
            event_is_set = self.event.wait()
            while self.getApproach()["approach"]:
                print("************ok")
                time.sleep(10)
                self.event.clear()
            self.actionEndFunc()


    def addWarnIdList(self, ID, context):
        self.warn_id_list[ID] = context

    def removeWarnIdList(self, ID, context):
        self.warn_id_list.pop(ID, None)

    def configCallback(self, update: Update, context: CallbackContext):
        global relay
        text = update.message.text
        # kích hoạt báo động
        if text == reply_keyboard[0][0]:
            self.addWarnIdList(update.message.chat.id, context)
            update.message.reply_text("đã kích hoạt báo động")
        # Hủy báo động
        elif text == reply_keyboard[0][1]:
            self.removeWarnIdList(update.message.chat.id, context)
            update.message.reply_text("đã hủy báo động")
        # kích hoạt quạt
        elif text == reply_keyboard[1][0]:
            self.actionFunc = relay.setOn
            self.actionEndFunc = relay.setOff
            update.message.reply_text("quạt sẽ được mở khi PIR được kích hoạt")
        # Hủy kích hoạt quạt
        elif text == reply_keyboard[1][1]:
            if self.actionFunc is not None:
                del self.actionFunc
            #del self.actionEndFunc
            update.message.reply_text("đã hủy kích hoạt quạt")
        return ConversationHandler.END

    def getApproach(self):
        url = self.base_url + "/approach?access_token=" + self.token
        return self.getData(url)

    def getApproachCallback(self, update: Update, context: CallbackContext):
        contents = self.getApproach()
        update.message.reply_text(json.dumps(contents))


WARN_ON, WARN_OFF, FAN_ON, END = range(4)
CHOOSING = range(1)

reply_keyboard = [
    ["kích hoạt báo động", "Hủy báo động"],
    ["kích hoạt quạt", "Hủy kích hoạt quạt"],
    ["Hủy"],
]
markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
relay = WioRelay(
    "https://us.wio.seeed.io/v1/node/GroveRelayD0",
    os.getenv("WIO_TOKEN"),
)
temp = WioTemp(
    "https://us.wio.seeed.io/v1/node/GroveTempA0",
    os.getenv("WIO_TOKEN"),
)
pir = WioPIR(
    "https://us.wio.seeed.io/v1/node/GrovePIRMotionD1",
    os.getenv("WIO_TOKEN"),
)


def pirConfig(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Hãy chọn tùy chỉnh bạn muốn thay đổi ", reply_markup=markup
    )
    return CHOOSING


def end(update: Update, context: CallbackContext):
    update.message.reply_text("cấu hình PIR kết thúc")
    return ConversationHandler.END


def main():
    updater = Updater(os.getenv("TELEGRAM_TOKEN"))
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("relay_on", relay.setOnCallback))
    dp.add_handler(CommandHandler("relay_off", relay.setOffCallback))
    dp.add_handler(CommandHandler("temp", temp.getTempCallback))
    dp.add_handler(CommandHandler("pir", pir.getApproachCallback))
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("pirconfig", pirConfig)],
        states={
            CHOOSING: [
                MessageHandler(
                    Filters.regex(
                        "^(kích hoạt báo động|Hủy báo động|kích hoạt quạt|Hủy kích hoạt quạt|Hủy)$"
                    ),
                    pir.configCallback,
                ),
            ],
        },
        fallbacks=[MessageHandler(Filters.regex("^Hủy$"), end)],
    )

    dp.add_handler(conv_handler)
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
