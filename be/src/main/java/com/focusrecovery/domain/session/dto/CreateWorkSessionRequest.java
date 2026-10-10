package com.focusrecovery.domain.session.dto;

import jakarta.validation.constraints.NotBlank;

public record CreateWorkSessionRequest(
	@NotBlank(message = "작업 목표를 입력해 주세요.")
	String goalText
) {
}
