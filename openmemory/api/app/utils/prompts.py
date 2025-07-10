MEMORY_CATEGORIZATION_PROMPT = """Your task is to assign each piece of information (or "memory") to one or more of the following categories. Feel free to use multiple categories per item when appropriate.

## 🎯 Core Life Domains (主要生活领域)
- Personal Identity: name, age, personal details, character traits, values, beliefs
- Relationships: family, friends, romantic partners, colleagues, social connections
- Health & Wellness: physical health, mental health, fitness, medical conditions, habits
- Career & Work: job roles, companies, projects, skills, professional goals, workplace
- Education & Learning: courses, degrees, certifications, skills development, knowledge

## 🎨 Personal Interests & Lifestyle (个人兴趣与生活方式)
- Hobbies & Interests: creative activities, sports, games, collections, pastimes
- Entertainment: movies, music, books, TV shows, podcasts, media preferences
- Food & Dining: dietary preferences, favorite foods, restaurants, cooking, nutrition
- Travel & Places: trips, destinations, commuting, favorite locations, geography

## 💼 Practical Life Management (实用生活管理)
- Finance & Money: income, expenses, investments, budgeting, financial goals
- Shopping & Purchases: buying preferences, wishlists, brands, consumer behavior
- Organization & Planning: schedules, appointments, to-dos, goals, time management
- Communication: messages, emails, calls, notifications, social media

## 🛠️ Specialized Knowledge (专业知识领域)
- Technology & Digital: software, hardware, tech preferences, digital tools, AI/ML
- Legal & Compliance: contracts, policies, regulations, privacy, legal matters
- Business & Professional: entrepreneurship, business ideas, industry knowledge
- Support & Services: customer service, technical support, problem-solving

## 📊 Information & Content (信息与内容)
- News & Current Events: headlines, trending topics, world events, social issues
- Knowledge & Facts: educational content, trivia, reference information
- Feedback & Reviews: product reviews, ratings, opinions, evaluations
- Goals & Aspirations: long-term objectives, ambitions, dreams, KPIs, milestones

Guidelines:
- 🎯 **Primary Focus**: Prioritize Core Life Domains for personal memories
- 🏷️ **Multi-Category**: Use 1-3 categories maximum per memory for clarity
- 📝 **Format**: Return only lowercase category names under 'categories' key in JSON format
- 🆕 **Flexibility**: Create new categories only if none of the above fit (use single phrase)
- 🔍 **Context-Aware**: Consider the memory's context and user intent
- ❌ **Empty Case**: Return empty list if memory cannot be categorized

Examples:
- "I love pizza" → ["food & dining", "personal identity"]
- "Meeting with John at 3pm" → ["organization & planning", "relationships"]
- "Graduated from MIT" → ["education & learning", "personal identity"]

/no_think
"""
