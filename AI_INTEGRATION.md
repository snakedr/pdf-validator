# 🤖 Гибкая AI/ML валидация в Email Processor

## 🎯 Концепция

Система теперь поддерживает любые AI/ML модели для валидации PDF документов, а не только OpenAI GPT.

## ⚙️ Конфигурация

### Основные параметры:
- `AI_PROVIDER` - тип провайдера (openai, anthropic, ollama, custom)
- `AI_API_KEY` - API ключ провайдера
- `AI_MODEL` - название модели
- `AI_BASE_URL` - URL API провайдера

### Примеры конфигураций:

#### 1. OpenAI (по умолчанию)
```env
AI_PROVIDER=openai
AI_API_KEY=sk-your-openai-key
AI_MODEL=gpt-4o-mini
AI_BASE_URL=https://api.openai.com/v1
```

#### 2. Anthropic Claude
```env
AI_PROVIDER=anthropic
AI_API_KEY=sk-ant-your-claude-key
AI_MODEL=claude-3-haiku-20240307
AI_BASE_URL=https://api.anthropic.com
```

#### 3. Ollama (локальные модели)
```env
AI_PROVIDER=ollama
AI_API_KEY=dummy-key
AI_MODEL=llama3.1:8b
AI_BASE_URL=http://localhost:11434/v1
```

#### 4. Custom API (Mistral, Groq, Gemini и др.)
```env
AI_PROVIDER=custom
AI_API_KEY=your-custom-key
AI_MODEL=mistral-large-latest
AI_BASE_URL=https://api.mistral.ai/v1
```

## 🔧 Техническая реализация

### Универсальный AI клиент (`ai_client.py`)
- Поддерживает разных провайдеров через единый интерфейс
- Автоматическая адаптация payload под каждый провайдер
- Обработка ошибок и fallback к детерминированной валидации

### Поддерживаемые провайдеры:
1. **OpenAI** - GPT-4o-mini, GPT-4, и другие
2. **Anthropic** - Claude 3 (Haiku, Sonnet, Opus)
3. **Ollama** - Любые локальные модели (Llama, Mistral, и др.)
4. **Custom** - Любой OpenAI-совместимый API

### Преимущества:
- 🔄 **Гибкость** - легко поменять провайдера
- 💰 **Экономия** - использовать локальные или более дешевые модели
- 🚀 **Производительность** - быстрые локальные модели
- 🛡️ **Надежность** - fallback к детерминированной валидации
- 🔌 **Расширяемость** - легко добавить новый провайдер

## 📋 Примеры использования

### Переключение между провайдерами:
```bash
# С OpenAI на Anthropic
cp .env.anthropic-example .env
docker-compose restart worker

# С Anthropic на локальную Ollama
cp .env.ollama-example .env
docker-compose restart worker
```

### Добавление нового провайдера:
1. Добавить логику в `ai_client.py`
2. Указать параметры в `.env.ai-examples`
3. Обновить документацию

## 🧪 Тестирование

Система автоматически тестирует:
- Корректность подключения к API
- Правильность формата ответа
- Совместимость модели с задачей
- Fallback при недоступности AI

## 📊 Сравнение провайдеров

| Провайдер | Скорость | Цена | Качество | Приватность |
|------------|----------|-------|------------|--------------|
| OpenAI GPT | Средняя | Высокая | Отличное | Облако |
| Claude | Средняя | Высокая | Отличное | Облако |
| Ollama | Быстрая | Бесплатно | Хорошее | Локально |
| Custom | Разная | Разная | Разное | Разное |

## 🚀 Быстрый старт

```bash
# 1. Выберите провайдер
cp .env.ai-examples .env

# 2. Настройте параметры
nano .env

# 3. Перезапустите worker
docker-compose restart worker

# 4. Проверьте логи
docker-compose logs worker
```

Система готова к работе с любым AI провайдером! 🎉