package com.focusrecovery.domain.session.service;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.focusrecovery.domain.session.dto.WorkSessionResponse;
import com.focusrecovery.domain.session.entity.WorkSession;
import com.focusrecovery.domain.session.exception.SessionNotFoundException;
import com.focusrecovery.domain.session.repository.WorkSessionRepository;

@Service
public class WorkSessionService {

	private final WorkSessionRepository workSessionRepository;

	public WorkSessionService(WorkSessionRepository workSessionRepository) {
		this.workSessionRepository = workSessionRepository;
	}

	@Transactional
	public WorkSessionResponse create(String goalText) {
		WorkSession session = workSessionRepository.save(WorkSession.start(goalText.strip()));
		return WorkSessionResponse.from(session);
	}

	@Transactional(readOnly = true)
	public WorkSessionResponse get(UUID sessionId) {
		return workSessionRepository.findById(sessionId)
			.map(WorkSessionResponse::from)
			.orElseThrow(SessionNotFoundException::new);
	}
}
