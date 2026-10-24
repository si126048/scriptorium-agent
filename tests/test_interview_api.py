import uuid

from scriptorium import api


def test_interview_api_handlers_lifecycle():
    project_id = f'api-interview-{uuid.uuid4().hex[:8]}'
    participant_id = f'p-{uuid.uuid4().hex[:8]}'
    assert api.project(api.ProjectIn(id=project_id))['id'] == project_id
    api.participant(api.ParticipantIn(id=participant_id, project_id=project_id))

    created = api.create_interview(api.InterviewCreateIn(
        project_id=project_id, participant_id=participant_id,
    ))
    session = created['session']
    session_id = session['id']
    assert session['state'] == 'CREATED'
    assert session['current_question']['id'] == 'Q1'

    answered = api.interview_turn(session_id, api.InterviewTurnIn(
        project_id=project_id, participant_id=participant_id,
        question_id='Q1', answer_text='简短回答',
    ))
    assert answered['current_question']['id'] == 'Q2'

    paused = api.pause_interview(session_id, api.InterviewAccessIn(
        project_id=project_id, participant_id=participant_id,
    ))
    assert paused['state'] == 'PAUSED'
    resumed = api.resume_interview(session_id, api.InterviewAccessIn(
        project_id=project_id, participant_id=participant_id,
    ))
    assert resumed['state'] == 'IN_PROGRESS'

    completed_data = api.create_interview(api.InterviewCreateIn(
        project_id=project_id, participant_id=participant_id,
    ))
    # Use a fresh session and short answers so the deterministic provider advances directly.
    complete_id = completed_data['session']['id']
    for question_id in ('Q1', 'Q2', 'Q3', 'Q4'):
        api.interview_turn(complete_id, api.InterviewTurnIn(
            project_id=project_id, participant_id=participant_id,
            question_id=question_id, answer_text='答复',
        ))
    completed = api.complete_interview(complete_id, api.InterviewAccessIn(
        project_id=project_id, participant_id=participant_id,
    ))
    assert completed['source_id'] and completed['run_id']

    reset = api.reset_interview(complete_id, api.InterviewAccessIn(
        project_id=project_id, participant_id=participant_id,
    ))
    assert reset['previous_session_id'] == complete_id
    assert reset['session']['id'] != complete_id
    assert reset['session']['state'] == 'CREATED'

    withdrawn = api.withdraw_interview(session_id, api.InterviewAccessIn(
        project_id=project_id, participant_id=participant_id,
    ))
    assert withdrawn['state'] == 'WITHDRAWN'
