from urllib.parse import urlencode
from typing import Any, AsyncGenerator

from port_ocean.context.event import event
from port_ocean.utils import http_async_client

from loguru import logger


class JenkinsClient:
    def __init__(
        self, jenkins_base_url: str, jenkins_user: str, jenkins_token: str
    ) -> None:
        self.jenkins_base_url = jenkins_base_url
        auth = (jenkins_user, jenkins_token)

        self.client = http_async_client
        self.client.auth = auth

    async def get_all_jobs_and_builds(
        self,
    ) -> AsyncGenerator[list[dict[str, Any]], None]:
        cache_key = "jenkins_jobs_and_builds"

        if cache := event.attributes.get(cache_key):
            logger.info("picking from cache")
            yield cache
            return

        page_size = 100
        page = 0

        all_jobs = []

        try:
            while True:
                start_idx = page_size * page
                end_idx = start_idx + page_size

                params = {
                    "tree": f"jobs[name,url,description,displayName,fullDisplayName,fullName,allBuilds[id,number,url,"
                    f"result,duration,timestamp,displayName,fullDisplayName]]{{{start_idx},{end_idx}}}"
                }

                job_response = await self.client.get(
                    f"{self.jenkins_base_url}/api/json?{urlencode(params)}"
                )
                job_response.raise_for_status()
                jobs = job_response.json()["jobs"]

                if not jobs:
                    break

                logger.info(f"Got {len(jobs)} jobs from Jenkins")
                all_jobs.extend(jobs)

                yield jobs
                page += 1

                if len(jobs) < page_size:
                    break
            event.attributes[cache_key] = all_jobs
        except Exception as e:
            logger.error(f"Unexpected error occurred: {e}")
            raise

    async def get_single_resource(self, resource_url: str) -> dict[str, Any]:
        """
        Get either a job or build using the url from the event e.g.

        Job: job/JobName/
        Build: job/JobName/34/
        """
        response = await self.client.get(
            f"{self.jenkins_base_url}/{resource_url}api/json"
        )
        response.raise_for_status()
        return response.json()
