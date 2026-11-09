// Migration: Add status_history field to candidates
// This field stores a unique set of statuses (VacancyStageEnum) the candidate has been in
// For existing candidates, we assume left-to-right movement through stages

const mainFlowOrder = [
    "magic-ai",
    "new",
    "selected",
    "message",
    "preliminary_call",
    "interview",
    "test_task",
    "final_test",
    "offer",
    "accepted"
];

const candidatesCollection = db.getCollection('candidates');

const cursor = candidatesCollection.find({
    'status_history': { $exists: false },
    'deleted_at': null
});

cursor.forEach(function(candidate) {
    const currentStatus = candidate.status;
    
    let statusHistory = [];
    
    if (currentStatus === "rejected") {
        statusHistory = ["magic-ai", "rejected"];
    } else {
        const currentIndex = mainFlowOrder.indexOf(currentStatus);
        
        if (currentIndex >= 0) {
            // Include all stages from the beginning up to and including current status
            statusHistory = mainFlowOrder.slice(0, currentIndex + 1);
        } else {
            // If status not found in order, just include current status
            statusHistory = [currentStatus];
        }
    }
    
    candidatesCollection.updateOne(
        { _id: candidate._id },
        { $set: { status_history: statusHistory } }
    );
});

print("Migration completed: status_history added to all candidates");
