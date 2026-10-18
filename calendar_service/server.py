"""Single browser owner, configurable port for Docker/Railway."""
import os
import uvicorn

if __name__=='__main__':
    uvicorn.run('calendar_service.api:app',host='0.0.0.0',port=int(os.environ.get('PORT','8080')),
        workers=1,timeout_graceful_shutdown=30)
