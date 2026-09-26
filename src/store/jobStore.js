export class InMemoryJobStore {
  constructor() {
    this.jobs = new Map();
  }

  create(job) {
    this.jobs.set(job.jobId, job);
    return job;
  }

  get(jobId) {
    return this.jobs.get(jobId) || null;
  }

  update(jobId, patch) {
    const job = this.jobs.get(jobId);
    if (!job) return null;
    Object.assign(job, patch, { updatedAt: new Date().toISOString() });
    return job;
  }

  delete(jobId) {
    return this.jobs.delete(jobId);
  }

  list() {
    return [...this.jobs.values()];
  }
}
