from __future__ import annotations

from typing import Optional

import httpx

from app.config import WORKLOG_API_BASE, WORKLOG_API_KEY


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {WORKLOG_API_KEY}",
        "Content-Type": "application/json",
    }


def _url(path: str) -> str:
    return f"{WORKLOG_API_BASE}{path}"


class WorklogError(Exception):
    pass


class WorklogClient:
    def __init__(self):
        self._client = httpx.Client(timeout=30)

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            resp = self._client.request(method, _url(path), headers=_headers(), **kwargs)
        except httpx.RequestError as e:
            raise WorklogError(f"请求失败: {e}")
        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = resp.json().get("error", resp.text)
            except Exception:
                pass
            raise WorklogError(f"API 错误 ({resp.status_code}): {detail}")
        if resp.status_code == 204:
            return {}
        return resp.json()

    def get_projects(self) -> list[dict]:
        return self._request("GET", "/projects").get("data", [])

    def get_users(self) -> list[dict]:
        return self._request("GET", "/users").get("data", [])

    def get_user(self, user_id: int) -> dict:
        return self._request("GET", f"/users/{user_id}").get("data", {})

    def get_tasks(self, project_id: int, status: Optional[str] = None) -> list[dict]:
        params = {}
        if status:
            params["status"] = status
        return self._request("GET", f"/projects/{project_id}/tasks", params=params).get("data", [])

    def create_task(self, project_id: int, data: dict) -> dict:
        return self._request("POST", f"/projects/{project_id}/tasks", json=data).get("data", {})

    def update_task(self, task_id: int, data: dict) -> dict:
        return self._request("PUT", f"/tasks/{task_id}", json=data).get("data", {})

    def delete_task(self, task_id: int) -> None:
        self._request("DELETE", f"/tasks/{task_id}")

    def get_logs(
        self,
        project_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        params: dict = {"limit": limit, "offset": offset}
        if project_id is not None:
            params["project_id"] = project_id
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self._request("GET", "/logs", params=params).get("data", [])

    def get_log(self, log_id: int) -> dict:
        return self._request("GET", f"/logs/{log_id}").get("data", {})

    def create_log(self, data: dict) -> dict:
        return self._request("POST", "/logs", json=data).get("data", {})

    def update_log(self, log_id: int, data: dict) -> dict:
        return self._request("PUT", f"/logs/{log_id}", json=data).get("data", {})

    def delete_log(self, log_id: int) -> None:
        self._request("DELETE", f"/logs/{log_id}")
