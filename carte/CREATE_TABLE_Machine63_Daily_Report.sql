CREATE TABLE Machine63_Daily_Report
(
ID INT IDENTITY(1,1) PRIMARY KEY,
MachineName VARCHAR(50),
ShiftDate DATETIME,
ProductionHours FLOAT,
StopHours FLOAT,
Availability FLOAT
);
