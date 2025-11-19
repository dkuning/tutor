from modules.storage import get_schedule_for_student, get_tutor


def get_tutor_info(tutor_id):
    """Возвращает информацию о репетиторе по ID."""
    return get_tutor(tutor_id)

def command_list_of_study(student_id):
    """Возвращает сообщение и список кнопок с предметами."""
    schedule = get_schedule_for_student(student_id)
    message = "выбери предмет из списка"

    buttons = []
    for item in schedule:
        tutor = get_tutor_info(item['tutor_id'])
        buttons.append({
            'text': f"{item['name']} ({tutor['name']})",
            'callback_data': f"subject_{item['subject_id']}"
        })

    return message, buttons


if __name__ == '__main__':
    print("Вызов")