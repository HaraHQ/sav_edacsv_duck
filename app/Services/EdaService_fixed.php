        return "SELECT \"AcReg\", 
                $limitCase as torque_limit,
                COUNT(CASE WHEN TRY_CAST(\"E1 Torq\" AS DOUBLE) > $limitCase THEN 1 END) as total_overlimit,
                ROUND(COUNT(CASE WHEN TRY_CAST(\"E1 Torq\" AS DOUBLE) > $limitCase THEN 1 END) / 60.0, 2) as total_overlimit_minutes
                FROM ($unionQuery) AS data
                GROUP BY \"AcReg\"";
