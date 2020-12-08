from mycroft import MycroftSkill, intent_file_handler


class Reservation(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)

    @intent_file_handler('reservation.intent')
    def handle_reservation(self, message):
        self.speak_dialog('reservation')


def create_skill():
    return Reservation()

