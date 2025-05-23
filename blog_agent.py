# -*- coding: utf-8 -*-
"""blog_agent.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1cWlPD2dF4HqyAp1prumTjUyzdLjfiYQc
"""

import os
import json
import time
import argparse
import requests
import google.generativeai as genai
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from typing import Union, List, Dict, Any, Optional
import asyncio
from tqdm import tqdm
import google.generativeai as genai
import functools
import asyncio
import time
import random

# Configuration
API_KEYS = {
    "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", ""),
    "NEWSDATA_API_KEY": os.environ.get("NEWSDATA_API_KEY", ""),
}

# Set up Gemini API
genai.configure(api_key=API_KEYS["GEMINI_API_KEY"])

from abc import ABC, abstractmethod

# Add this decorator implementation before the BaseAgent class
def retry_with_backoff(max_retries=3, base_delay=1):
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    wait_time = base_delay * 2 ** retries + random.uniform(0, 1)
                    print(f"Retry {retries+1}/{max_retries} failed. Waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                    retries += 1
            return await func(*args, **kwargs)  # Final attempt

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    wait_time = base_delay * 2 ** retries + random.uniform(0, 1)
                    print(f"Retry {retries+1}/{max_retries} failed. Waiting {wait_time:.2f}s")
                    time.sleep(wait_time)
                    retries += 1
            return func(*args, **kwargs)  # Final attempt

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

# Then keep the rest of your existing code


class BaseAgent(ABC):
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def run(self, *args, **kwargs):
        pass

class BlogAgent(BaseAgent):
    """Main agent orchestrating the blog writing process"""

    def __init__(self,
                 topic: Union[str, List[str]],
                 tone: Optional[str] = "informative",
                 context_agent: Optional["ContextAgent"] = None,
                 writing_agent: Optional["WritingAgent"] = None,
                 seo_agent: Optional["SEOAgent"] = None,
                 readability_agent: Optional["ReadabilityAgent"] = None,
                 execution_agent: Optional["ExecutionAgent"] = None,
                 config: Dict[str, Any] = None):

        super().__init__(config)

        self.topics = [topic] if isinstance(topic, str) else topic
        self.tone = tone
        self.context_agent = context_agent or ContextAgent(config)
        self.writing_agent = writing_agent or WritingAgent(config)
        self.seo_agent = seo_agent or SEOAgent(config)
        self.readability_agent = readability_agent or ReadabilityAgent(config)
        self.execution_agent = execution_agent or ExecutionAgent(config)

        # Ensure output directories exist
        os.makedirs("output/blogs", exist_ok=True)
        os.makedirs("output/metadata", exist_ok=True)

    async def run(self):
        """Execute the full blog creation pipeline for all topics"""
        results = []

        for topic in tqdm(self.topics, desc="Processing topics"):
            print(f"\n🤖 Starting Blog Agent for topic: '{topic}'")
            print(f"🎭 Using tone: {self.tone}")

            blog_data = {
                "topic": topic,
                "tone": self.tone,
                "title": "",
                "meta_description": "",
                "keywords": [],
                "slug": "",
                "reading_time": 0,
                "content": "",
                "created_at": datetime.now().isoformat(),
            }

            # Create semaphore to limit concurrent API calls
            semaphore = asyncio.Semaphore(self.config.get("concurrent_limit", 5))

            try:
                # Step 1: Topic Analysis
                print("\n📋 Step 1: Analyzing topic and planning content...")
                topic_analysis = await self._analyze_topic(topic, semaphore)

                # Step 2: Research (concurrent)
                print("\n🔍 Step 2: Conducting research...")
                research_data = await self.context_agent.gather_context(
                    topic,
                    topic_analysis["subtopics"],
                    semaphore
                )

                # Step 3: Content Generation
                print("\n✍️ Step 3: Generating content...")
                blog_content = await self.writing_agent.generate_blog(
                    topic,
                    topic_analysis["subtopics"],
                    research_data,
                    self.tone,
                    semaphore
                )
                blog_data["content"] = blog_content

                # Step 4: SEO Optimization
                print("\n🔎 Step 4: Optimizing for SEO...")
                seo_data = await self.seo_agent.optimize(topic, blog_content, semaphore)
                blog_data.update(seo_data)

                # Step 5: Readability Analysis
                print("\n📊 Step 5: Analyzing readability...")
                readability_data = await self.readability_agent.analyze(blog_content)
                blog_data.update(readability_data)

                # Step 6: Export and Summarize
                print("\n💾 Step 6: Exporting final blog...")
                output_files = await self.execution_agent.export(blog_data)

                print("\n✅ Blog creation complete!")
                print(f"📝 Title: {blog_data['title']}")
                print(f"⏱️ Reading time: {blog_data['reading_time']} minutes")
                print(f"🔗 Suggested URL: {blog_data['slug']}")

                if 'readability_scores' in blog_data:
                    print("\n📊 Readability Scores:")
                    for score_name, score_value in blog_data['readability_scores'].items():
                        print(f" - {score_name}: {score_value:.2f}")

                results.append(blog_data)

            except Exception as e:
                print(f"⚠️ Error processing topic '{topic}': {str(e)}")
                continue

        return results

    @retry_with_backoff()
    async def _analyze_topic(self, topic: str, semaphore: asyncio.Semaphore) -> Dict[str, Any]:
        """Analyze the topic and break it down into subtopics with retry logic"""
        async with semaphore:
            prompt = f"""
            You are a content strategist planning a blog post about "{topic}".
            1. Break this topic into 4-6 logical subtopics that would make good H2 headings.
            2. Determine the appropriate tone for this content: {self.tone}
            3. Identify the target audience and their knowledge level.

            Format your response as JSON with the following structure:
            {{
                "subtopics": ["subtopic1", "subtopic2", ...],
                "audience": "description of target audience",
                "knowledge_level": "beginner|intermediate|advanced"
            }}
            """

            model = genai.GenerativeModel('gemini-2.0-flash-001')
            response = await asyncio.to_thread(model.generate_content, prompt)

            try:
                analysis = json.loads(response.text)
                print(f"📌 Identified {len(analysis['subtopics'])} subtopics")
                print(f"👥 Target audience: {analysis['audience']}")
                print(f"📚 Knowledge level: {analysis['knowledge_level']}")
                return analysis
            except json.JSONDecodeError:
                print("⚠️ Error parsing topic analysis. Using default structure.")
                return {
                    "subtopics": [
                        f"Understanding {topic}",
                        f"Benefits of {topic}",
                        f"Challenges with {topic}",
                        f"Future of {topic}"
                    ],
                    "audience": "General readers interested in the topic",
                    "knowledge_level": "intermediate"
                }

        model = genai.GenerativeModel('gemini-2.0-flash-001')
        response = model.generate_content(prompt)

        try:
            analysis = json.loads(response.text)
            print(f"📌 Identified {len(analysis['subtopics'])} subtopics")
            print(f"👥 Target audience: {analysis['audience']}")
            print(f"📚 Knowledge level: {analysis['knowledge_level']}")
            return analysis
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            print("⚠️ Error parsing topic analysis. Using default structure.")
            return {
                "subtopics": [f"Understanding {self.topic}",
                             f"Benefits of {self.topic}",
                             f"Challenges with {self.topic}",
                             f"Future of {self.topic}"],
                "audience": "General readers interested in the topic",
                "knowledge_level": "intermediate"
            }

