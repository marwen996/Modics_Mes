-- =====================================================================
-- MODICS - état temps réel des machines (dashboard "toutes les machines")
-- La table est aussi créée automatiquement par moul.py au 1er envoi.
-- 1 ligne par machine, mise à jour dès qu'un arrêt est déclaré (< 1 s)
-- + heartbeat toutes les 10 s.
-- =====================================================================
IF OBJECT_ID('dbo.Machine_Live_State_Mould') IS NULL
CREATE TABLE dbo.Machine_Live_State_Mould (
    Machine_Name_Mould  NVARCHAR(50)  NOT NULL PRIMARY KEY,
    State_Mould         NVARCHAR(30)  NULL,
    Code_Stop_Mould     NVARCHAR(60)  NULL,
    Stop_Start_Mould    DATETIME      NULL,
    Shop_Order_Mould    NVARCHAR(50)  NULL,
    Part_Number_Mould   NVARCHAR(50)  NULL,
    Shift_Mould         NVARCHAR(20)  NULL,
    Is_Planned_Mould    BIT           NOT NULL DEFAULT 0,
    Updated_Mould       DATETIME      NOT NULL DEFAULT GETDATE()
);
GO

-- Vue à lire par le dashboard : une carte par ligne, couleur déjà calculée.
CREATE OR ALTER VIEW dbo.v_Machine_Live_State AS
SELECT  l.Machine_Name_Mould,
        l.Shop_Order_Mould, l.Part_Number_Mould, l.Shift_Mould, l.Is_Planned_Mould,
        l.Stop_Start_Mould,
        DATEDIFF(MINUTE, l.Stop_Start_Mould, GETDATE())             AS Stop_Minutes,
        DATEDIFF(SECOND, l.Updated_Mould, GETDATE())                AS Age_s,
        -- Pi éteint / réseau coupé : plus de heartbeat depuis 45 s
        CASE WHEN DATEDIFF(SECOND, l.Updated_Mould, GETDATE()) > 45 THEN N'Machine OFF'
             ELSE l.State_Mould END                                 AS Display_State,
        CASE WHEN DATEDIFF(SECOND, l.Updated_Mould, GETDATE()) > 45 THEN NULL
             ELSE l.Code_Stop_Mould END                             AS Code_Stop_Mould,
        CASE
            WHEN DATEDIFF(SECOND, l.Updated_Mould, GETDATE()) > 45 THEN '#64748B'  -- hors ligne
            WHEN l.State_Mould = N'Production'                     THEN '#22C55E'  -- en production
            WHEN l.State_Mould = N'Aucun OF'                       THEN '#334155'  -- pas d'OF
            WHEN l.Code_Stop_Mould = N'Maintenance'                THEN '#EAB308'
            WHEN l.Code_Stop_Mould = N'Mécanique'                  THEN '#F97316'
            WHEN l.Code_Stop_Mould = N'Qualité'                    THEN '#A855F7'
            WHEN l.Code_Stop_Mould = N'Process'                    THEN '#06B6D4'
            WHEN l.Code_Stop_Mould = N'Production'                 THEN '#EC4899'
            WHEN l.Code_Stop_Mould = N'Arrêt planifié'             THEN '#6B8FD6'
            ELSE '#DC2626'                                                          -- arrêt non déclaré
        END                                                         AS Card_Color
FROM dbo.Machine_Live_State_Mould l;
GO

-- Test : SELECT * FROM dbo.v_Machine_Live_State;
